"""Exploratory within-industry financial screening; no TP outcome labels exist."""
from pathlib import Path
import hashlib
import json
import math
import warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score, adjusted_rand_score
from sklearn.neural_network import MLPRegressor
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits
from financial_criteria import criteria_features,CRITERIA_FEATURES,company_history_frame
from sklearn_pipelines import make_preprocessor,make_model_pipeline,MaskedReconstructionRegressor,fit_neural

SEED=20261111
METHODS=['masked_reconstruction','autoencoder','isolation_forest']
RATIO_FEATURES=['return_on_assets_pct','return_on_equity_pct','gross_margin_pct','operating_margin_pct','net_margin_pct',
 'current_ratio','receivables_turnover','inventory_turnover','payables_turnover','asset_turnover',
 'operating_expense_ratio_pct','assets_to_equity','liabilities_to_assets','liabilities_to_equity','liabilities_to_working_capital']

def feature_frame(data):
    result=data.reindex(columns=RATIO_FEATURES).apply(pd.to_numeric,errors='coerce')
    revenue=pd.to_numeric(data.get('revenue',pd.Series(np.nan,index=data.index)),errors='coerce')
    # Preserve zero/negative revenue and compare net losses as well as profits.
    result.loc[revenue.eq(0),['gross_margin_pct','operating_margin_pct','net_margin_pct','operating_expense_ratio_pct']]=np.nan
    # Keep source amounts intact, but do not learn from a disputed gross-margin input.
    if all(field in data for field in ['primary_revenue','cost_of_sales','gross_profit']):
        gross_check=data[['primary_revenue','cost_of_sales','gross_profit']].apply(pd.to_numeric,errors='coerce')
        disputed=gross_check.notna().all(axis=1) & (gross_check.primary_revenue-gross_check.cost_of_sales-gross_check.gross_profit).abs().gt(.05)
        result.loc[disputed,'gross_margin_pct']=np.nan
    profit=pd.to_numeric(data.get('net_profit',pd.Series(np.nan,index=data.index)),errors='coerce')
    result['signed_log_net_profit_thb']=np.sign(profit)*np.log1p(np.abs(profit))
    result['signed_log_revenue_thb']=np.sign(revenue)*np.log1p(np.abs(revenue))
    order=['signed_log_net_profit_thb','signed_log_revenue_thb']+RATIO_FEATURES
    return result[order].join(criteria_features(data)).replace([np.inf,-np.inf],np.nan)

def transform(frame,bundle):
    raw=feature_frame(frame)[bundle['features']].to_numpy(dtype=float)
    missing=~np.isfinite(raw)
    if 'preprocessor' in bundle:z=bundle['preprocessor'].transform(frame)
    else:
        # Compatibility for previously saved research bundles.
        filled=np.where(missing,bundle['median'],raw)
        z=np.arcsinh((filled-bundle['median'])/bundle['scale'])
    return z,missing,raw

def scores(z,missing,bundle,frame=None):
    if frame is not None and 'pipelines' in bundle:
        prediction=bundle['pipelines']['masked_reconstruction'].predict(frame)[-len(z):]
        ae_prediction=bundle['pipelines']['autoencoder'].predict(frame)[-len(z):]
        forest_score=-bundle['pipelines']['isolation_forest'].score_samples(frame)[-len(z):]
    else:
        prediction=np.column_stack([model.predict(np.delete(z,j,axis=1)) for j,model in enumerate(bundle['masked_models'])])
        ae_prediction=bundle['autoencoder'].predict(z);forest_score=-bundle['isolation_forest'].score_samples(z)
    errors=np.where(~missing,(prediction-z)**2,np.nan)
    ae_errors=np.where(~missing,(ae_prediction-z)**2,np.nan)
    result={'masked_reconstruction':np.nanmean(errors,axis=1),'autoencoder':np.nanmean(ae_errors,axis=1),
            'isolation_forest':forest_score}
    if 'references' in bundle:
        percentiles=[np.searchsorted(bundle['references'][name],result[name],side='right')/len(bundle['references'][name]) for name in METHODS]
        result['consensus']=np.mean(percentiles,axis=0)
    return result,errors

def assign_splits(companies):
    rows=[]
    for pool,group in companies.groupby('nature_pool',sort=True):
        ids=sorted(group.registration_number.tolist());rng=np.random.default_rng(SEED)
        ids=np.array(ids)[rng.permutation(len(ids))];n=len(ids);ntrain=int(n*.6);ncal=int(n*.2)
        for i,reg in enumerate(ids):rows.append({'registration_number':reg,'nature_pool':pool,'split':'train' if i<ntrain else 'calibration' if i<ntrain+ncal else 'test'})
    return pd.DataFrame(rows)

def select_training_features(training):
    candidates=feature_frame(training);feature_audit=[];selected=[]
    # Feature selection uses training rows only; near-duplicate ratios cannot dominate distances.
    for feature in candidates:
        values=candidates[feature]
        reason='retained'
        minimum=.4 if feature in CRITERIA_FEATURES else .8
        if values.notna().mean()<minimum:reason='insufficient_observed_training_targets'
        elif values.nunique()<3:reason='training_near_constant'
        else:
            for prior in selected:
                corr=values.corr(candidates[prior],method='spearman')
                if pd.notna(corr) and abs(corr)>.98:reason='training_redundancy_with_'+prior;break
        if reason=='retained':selected.append(feature)
        feature_audit.append(dict(feature=feature,selection=reason))
    assert len(selected)>=4,'Insufficient nonredundant features'
    return selected,feature_audit

def fit_pool(frame, pool, out):
    train=frame['split'].eq('train').to_numpy();cal=frame['split'].eq('calibration').to_numpy();test=frame['split'].eq('test').to_numpy()
    candidates=feature_frame(frame);selected,feature_audit=select_training_features(frame.loc[train])
    for row in feature_audit:row['nature_pool']=pool
    preprocessor=make_preprocessor(selected).fit(frame.loc[train])
    scaler=preprocessor.named_steps['columns'].named_transformers_['financial_numeric'].named_steps['robust_scaler']
    b={'features':selected,'median':scaler.center_,'scale':scaler.scale_,'nature_pool':pool,'min_observed':max(4,math.ceil(.5*len(selected))),
       'preprocessor':preprocessor,'pipelines':{}}
    z,missing,raw_all=transform(frame,b)
    assert (np.sum(~missing,axis=1)>=b['min_observed']).all()
    cluster_trials=[];kmodels={}
    for k in [2,3,4]:
        pipe=make_model_pipeline(preprocessor,KMeans(n_clusters=k,n_init=20,random_state=SEED)).fit(frame.loc[train]);model=pipe.named_steps['model'];labels=model.labels_
        sizes=pd.Series(labels).value_counts()
        score=silhouette_score(z[train],labels) if len(sizes)>1 else -1
        admissible=sizes.min()>=10
        cluster_trials.append(dict(nature_pool=pool,k=k,train_silhouette=score,minimum_training_rows=int(sizes.min()),admissible=admissible))
        if admissible:kmodels[k]=(pipe,score)
    if not kmodels:
        # Do not force an unstable tiny financial-pattern cluster in a skewed pool.
        kmodels[1]=(make_model_pipeline(preprocessor,KMeans(n_clusters=1,n_init=20,random_state=SEED)).fit(frame.loc[train]),float('nan'))
        cluster_trials.append(dict(nature_pool=pool,k=1,train_silhouette=None,minimum_training_rows=int(train.sum()),admissible=True))
    chosen=max(kmodels,key=lambda k:kmodels[k][1]);b['pipelines']['kmeans']=kmodels[chosen][0];b['kmeans']=kmodels[chosen][0].named_steps['model']
    stability=[]
    for seed in [11,22,33]:
        other=KMeans(n_clusters=chosen,n_init=20,random_state=seed).fit(z[train])
        stability.append(adjusted_rand_score(b['kmeans'].predict(z[test]),other.predict(z[test])))
    training_warnings=[];optimization_attempts=[]
    masked=make_model_pipeline(preprocessor,MaskedReconstructionRegressor(feature_names=selected,random_state=SEED))
    masked.fit(frame.loc[train],model__observed_mask=~missing[train]);b['pipelines']['masked_reconstruction']=masked
    masked_model=masked.named_steps['model'];b['masked_models']=masked_model.estimators_
    training_warnings += [dict(nature_pool=pool,**row) for row in masked_model.training_warnings_]
    optimization_attempts += [dict(nature_pool=pool,**row) for row in masked_model.optimization_attempts_]
    auto_pipe=make_model_pipeline(preprocessor,MLPRegressor(hidden_layer_sizes=(8,3,8),activation='tanh',solver='lbfgs',alpha=1,max_iter=3000,max_fun=100000,tol=.001,random_state=SEED))
    auto_pipe,unresolved,attempts=fit_neural(auto_pipe,frame.loc[train],z[train],name='autoencoder')
    training_warnings += [dict(nature_pool=pool,**row) for row in unresolved];optimization_attempts += [dict(nature_pool=pool,**row) for row in attempts]
    b['pipelines']['autoencoder']=auto_pipe;b['autoencoder']=auto_pipe.named_steps['model']
    forest=make_model_pipeline(preprocessor,IsolationForest(n_estimators=300,random_state=SEED,n_jobs=1)).fit(frame.loc[train])
    b['pipelines']['isolation_forest']=forest;b['isolation_forest']=forest.named_steps['model']
    raw_scores,_=scores(z,missing,b,frame)
    b['references']={name:np.sort(raw_scores[name][cal]) for name in METHODS}
    all_scores,errors=scores(z,missing,b,frame)
    b['thresholds']={name:float(np.quantile(values[cal],.95,method='higher')) for name,values in all_scores.items()}
    b['training_min']=np.nanmin(raw_all[train],axis=0);b['training_max']=np.nanmax(raw_all[train],axis=0)
    b['training_feature_median_z']=np.median(z[train],axis=0)
    from financial_decision_rules import fit_benchmarks
    b['financial_rule_benchmarks']=fit_benchmarks(frame.loc[train])
    b['cluster_stability_test_ari']=stability;b['training_warnings']=training_warnings;b['optimization_attempts']=optimization_attempts
    result=frame.copy();result['cluster']=b['pipelines']['kmeans'].predict(frame);result['observed_model_features']=np.sum(~missing,axis=1)
    for feature in CRITERIA_FEATURES:result[feature]=candidates[feature].to_numpy()
    result['feature_count']=len(selected)
    result['largest_masked_error_feature']=[selected[j] for j in np.nanargmax(errors,axis=1)]
    deviations=np.abs(z-b['kmeans'].cluster_centers_[result['cluster']]);deviations[missing]=-np.inf
    result['largest_cluster_deviation_feature']=[selected[j] for j in np.argmax(deviations,axis=1)]
    result['outside_training_range_count']=np.sum((raw_all<b['training_min'])|(raw_all>b['training_max']),axis=1)
    metrics=[]
    baseline=np.nanmean(np.where(~missing,(z-b['training_feature_median_z'])**2,np.nan),axis=1)
    for name,values in all_scores.items():
        result[name+'_score']=values;result[name+'_flag']=values>b['thresholds'][name]
        if name in METHODS:result[name+'_percentile']=np.searchsorted(b['references'][name],values,side='right')/len(b['references'][name])
        metrics.append(dict(nature_pool=pool,model=name,train_companies=frame.loc[train,'registration_number'].nunique(),
            calibration_companies=frame.loc[cal,'registration_number'].nunique(),test_companies=frame.loc[test,'registration_number'].nunique(),
            train_rows=int(train.sum()),calibration_rows=int(cal.sum()),test_rows=int(test.sum()),threshold=b['thresholds'][name],
            test_flagged_rows=int((values[test]>b['thresholds'][name]).sum()),test_flag_rate=float((values[test]>b['thresholds'][name]).mean()),
            test_reconstruction_mse=float(values[test].mean()) if name in METHODS[:2] else None,
            training_median_baseline_test_mse=float(baseline[test].mean()) if name in METHODS[:2] else None,
            cluster_k=chosen,cluster_train_silhouette=kmodels[chosen][1],minimum_seed_test_cluster_ari=min(stability)))
    profiles=frame[['nature_pool']].copy();profiles['cluster']=result['cluster']
    for name in selected:profiles[name]=candidates[name].to_numpy()
    profiles=profiles.groupby(['nature_pool','cluster']).median().reset_index()
    return b,result,metrics,cluster_trials,feature_audit,training_warnings,profiles

def screen_new_company(company,bundle):
    """Frozen inference only. Supply ratios in reported percent/times, revenue in THB."""
    pool=company.get('nature_pool');answer={'registration_number':str(company.get('registration_number','')),'nature_pool':pool,'status':'ABSTAIN',
        'tp_status':'NOT_DETERMINED','financial_screening_flag':None,'model_version':bundle['version']}
    if pool not in bundle['pools']:answer['reason']='Unknown business-nature pool; verify original TSIC and business nature.';return answer
    for feature in RATIO_FEATURES+['revenue','net_profit','primary_revenue','cost_of_sales','gross_profit','selling_and_administrative_expenses','interest_expense','profit_before_tax']:
        value=company.get(feature)
        if value is not None and not (isinstance(value,str) and value.strip()=='') and not pd.isna(value):
            if isinstance(value,(bool,np.bool_)):raise ValueError(feature+' must be numeric, not boolean')
            try:number=float(value)
            except (TypeError,ValueError):raise ValueError(feature+' must be numeric or blank') from None
            if not np.isfinite(number):raise ValueError(feature+' must be finite or blank')
    if any(pd.isna(company.get(field)) or str(company.get(field)).strip()=='' for field in ['revenue','net_profit']):
        answer['reason']='Observed revenue and net profit in THB are required, including reported zeros or losses.';return answer
    try:year=float(company.get('fiscal_year',np.nan))
    except (ValueError,TypeError):year=float('nan')
    if not np.isfinite(year) or not year.is_integer() or int(year) not in range(2021,2026):
        answer['reason']='Supply a fiscal year within the audited FY2021-FY2025 range; later-year validation is required.';return answer
    b=bundle['pools'][pool];frame=company_history_frame(company);z,missing,raw=transform(frame,b)
    z=z[[-1]];missing=missing[[-1]];raw=raw[[-1]]
    observed=int((~missing).sum());answer['observed_features']=observed;answer['required_features']=b['min_observed']
    if observed<b['min_observed']:answer['reason']='Too few observed model features; missing inputs remain missing.';return answer
    with threadpool_limits(limits=1):
        values,errors=scores(z,missing,b,frame);cluster=int(b['pipelines']['kmeans'].predict(frame)[-1]) if 'pipelines' in b else int(b['kmeans'].predict(z)[0])
    answer.update(status='SCORED',cluster=cluster,financial_screening_flag=bool(values['consensus'][0]>b['thresholds']['consensus']),
        models={name:{'score':float(value[0]),'threshold':b['thresholds'][name],'flag':bool(value[0]>b['thresholds'][name])} for name,value in values.items()},
        largest_masked_error_feature=b['features'][int(np.nanargmax(errors[0]))],
        outside_training_range_count=int(np.sum((raw<b['training_min'])|(raw>b['training_max']))),
        training_warning_count=len(b['training_warnings']),
        scope='Broad financial-pattern comparison within supplied business-nature pool; not a TP compliance determination.')
    from financial_decision_rules import evaluate_rules
    answer['financial_rules']=evaluate_rules(company,feature_frame(frame).iloc[-1].to_dict(),b['financial_rule_benchmarks'],answer['financial_screening_flag'])
    return answer

def train_models(clean_dir, output_dir):
    clean=Path(clean_dir);out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv(clean/'Model_input_all_items.csv',dtype={'registration_number':str,'tsic_code':str})
    coverage=pd.read_csv(clean/'Company_coverage.csv',dtype={'registration_number':str})
    complete=coverage[coverage['five_year_core_complete']].registration_number
    cohort=data[data.registration_number.isin(complete)].copy()
    zero_revenue=cohort[cohort['revenue'].eq(0)].copy();zero_revenue['review_reason']='Zero revenue retained; revenue-based margins undefined'
    active=cohort.copy();companies=active[['registration_number','nature_pool']].drop_duplicates()
    assert not companies.registration_number.duplicated().any()
    splits=assign_splits(companies);active=active.merge(splits,on=['registration_number','nature_pool'],validate='many_to_one')
    split_ids={s:set(splits.loc[splits['split'].eq(s),'registration_number']) for s in ['train','calibration','test']}
    assert not (split_ids['train']&split_ids['test'] or split_ids['train']&split_ids['calibration'] or split_ids['test']&split_ids['calibration'])
    bundle={'version':'thai-exploratory-v2-pipeline-20261111','seed':SEED,'pools':{},'input_sha256':hashlib.sha256((clean/'Model_input_all_items.csv').read_bytes()).hexdigest()}
    results=[];metrics=[];trials=[];features=[];warnings_all=[];profiles=[]
    with threadpool_limits(limits=1):
        for pool,frame in active.groupby('nature_pool',sort=True):
            print('Training '+pool+': '+str(frame.registration_number.nunique())+' companies',flush=True)
            b,result,m,c,f,w,p=fit_pool(frame.reset_index(drop=True),pool,out)
            bundle['pools'][pool]=b;results.append(result);metrics+=m;trials+=c;features+=f;warnings_all+=w;profiles.append(p)
    result=pd.concat(results,ignore_index=True);metric=pd.DataFrame(metrics)
    from financial_decision_rules import evaluate_rules
    decisions=[]
    for row in result.to_dict('records'):
        decision=evaluate_rules(row,row,bundle['pools'][row['nature_pool']]['financial_rule_benchmarks'],row['consensus_flag'])
        for item in decision['rules']:decisions.append({'registration_number':row['registration_number'],'fiscal_year':row['fiscal_year'],'nature_pool':row['nature_pool'],'split':row['split'],**item})
    pd.DataFrame(decisions).to_csv(out/'Explainable_financial_rule_results.csv',index=False,encoding='utf-8-sig')
    routes=[]
    for row in result.to_dict('records'):
        decision=evaluate_rules(row,row,bundle['pools'][row['nature_pool']]['financial_rule_benchmarks'],row['consensus_flag'])
        routes.append({'registration_number':row['registration_number'],'fiscal_year':row['fiscal_year'],'nature_pool':row['nature_pool'],'split':row['split'],
                       'financial_review_route':decision['financial_review_route'],'indicator_count':decision['indicator_count'],
                       'triggered_rules':';'.join(decision['indicator_triggers']),'unassessable_rules':';'.join(decision['unassessable_rules'])})
    pd.DataFrame(routes).to_csv(out/'Explainable_financial_review_routes.csv',index=False,encoding='utf-8-sig')
    # Review concepts are descriptive. No related-party transactions are inferred.
    result['loss_year']=result['net_profit'].lt(0)
    loss_counts=cohort.groupby('registration_number')['net_profit'].agg(lambda x:int(x.lt(0).sum()))
    result['loss_years_in_observed_five_year_history']=result.registration_number.map(loss_counts)
    low_margin={pool:float(frame.loc[frame['split'].eq('train'),'net_margin_pct'].quantile(.1)) for pool,frame in result.groupby('nature_pool')}
    result['below_training_industry_net_margin_p10']=result['net_margin_pct']<result.nature_pool.map(low_margin)
    result['related_party_context']='UNKNOWN_REQUIRES_ANALYST_INPUT';result['tp_compliance_verdict']='NOT_DETERMINED'
    result['uk_review_alignment']='Financial pattern only; related-party dealings, functions/assets/risks and commercial explanation not verified'
    company=result.groupby(['registration_number','nature_pool','split'],as_index=False).agg(company_name=('company_name','first'),active_years=('fiscal_year','size'),
        consensus_flagged_years=('consensus_flag','sum'),maximum_consensus_score=('consensus_score','max'),loss_years=('loss_years_in_observed_five_year_history','first'))
    company['any_year_financial_flag']=company['consensus_flagged_years'].gt(0)
    # Any-year flags are summaries of annual screens, not separately calibrated company probabilities.
    pool_summary=company.groupby(['nature_pool','split'],as_index=False).agg(companies=('registration_number','size'),flagged_companies=('any_year_financial_flag','sum'))
    for name,frame in {'Annual_model_scores':result,'Company_model_summary':company,'Model_test_metrics':metric,'Cluster_selection':pd.DataFrame(trials),
        'Feature_selection':pd.DataFrame(features),'Training_warnings':pd.DataFrame(warnings_all,columns=['nature_pool','model','warning']),
        'Cluster_profiles':pd.concat(profiles,ignore_index=True),'Company_splits':splits,'Zero_revenue_years_retained':zero_revenue,'Industry_flags':pool_summary}.items():
        frame.to_csv(out/(name+'.csv'),index=False,encoding='utf-8-sig',lineterminator='\n')
    pd.DataFrame([entry for b in bundle['pools'].values() for entry in b['optimization_attempts']],columns=['nature_pool','model','initial_solver','warning','action']).to_csv(out/'Optimizer_attempts.csv',index=False,encoding='utf-8-sig')
    joblib.dump(bundle,out/'thai_industry_models.joblib',compress=3)
    test=result[result['split'].eq('test')];test_company=company[company['split'].eq('test')]
    summary={'model_version':bundle['version'],'source_complete_companies':int(len(complete)),'model_companies':len(companies),'model_company_years':len(active),
      'zero_revenue_company_years_retained':len(zero_revenue),'zero_revenue_years_excluded':0,
      'companies_by_split':splits['split'].value_counts().to_dict(),'held_out_test_companies':len(test_company),'held_out_test_company_years':len(test),
      'test_consensus_flagged_years':int(test['consensus_flag'].sum()),'test_companies_with_any_year_flag':int(test_company['any_year_financial_flag'].sum()),
      'training_warning_count':len(warnings_all),'industry_pools':len(bundle['pools']),'company_split_overlap':0,
      'history_features_use_strict_prior_years':True,'manual_criteria_used_as_training_labels':False,
      'implementation':'Explicit scikit-learn Pipeline and ColumnTransformer; financial columns only; remainder=drop',
      'financial_rule_benchmarks_use_training_only':True,'phase':'PHASE_1_FINANCIAL_MODEL',
      'retained_derived_criteria_by_pool':{pool:[name for name in b['features'] if name in CRITERIA_FEATURES] for pool,b in bundle['pools'].items()},
      'labelled_tp_outcomes':0,'tp_accuracy_available':False,'evaluation_scope':'Held-out companies within FY2021-FY2025; not future-year validation.',
      'threshold_scope':'Per-industry 95th-percentile calibration annual scores; correlated company years, no formal error-rate guarantee.',
      'deployment_status':'EXPLORATORY_REQUIRES_ADVISOR_AND_SOURCE_REVIEW','input_sha256':bundle['input_sha256']}
    (out/'model_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    example=test.iloc[0].to_dict();answer=screen_new_company(example,bundle)
    assert answer['status']=='SCORED'
    for method in METHODS+['consensus']:assert np.isclose(answer['models'][method]['score'],example[method+'_score'])
    (out/'Frozen_inference_example.json').write_text(json.dumps(answer,indent=2,ensure_ascii=False),encoding='utf-8')
    columns=['registration_number','nature_pool','fiscal_year','revenue','net_profit','primary_revenue','cost_of_sales','gross_profit','selling_and_administrative_expenses','profit_before_tax','interest_expense']+RATIO_FEATURES
    result[result.registration_number.eq(example['registration_number'])][columns].to_csv(out/'New_company_input_example.csv',index=False,encoding='utf-8-sig')
    print(json.dumps(summary,indent=2));return summary
