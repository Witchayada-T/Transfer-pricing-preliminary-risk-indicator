"""Phase-1 explainable financial rules; no legal-risk class or manual-data imputation."""
import math
import numpy as np
import pandas as pd
from financial_criteria import criteria_features

VERSION='financial-review-rules-v1'

def number(value):
    try:value=float(value)
    except (ValueError,TypeError):return None
    return value if math.isfinite(value) else None

def fit_benchmarks(training):
    """Only training-company values define peer comparison thresholds."""
    derived=criteria_features(training);margin=pd.to_numeric(training.net_margin_pct,errors='coerce').where(training.revenue.ne(0))
    leverage=pd.to_numeric(training.liabilities_to_equity,errors='coerce').where(lambda x:x>0)
    series={'net_margin_lower_p10':(margin,.1),'positive_leverage_upper_p90':(leverage,.9),
      'selling_admin_burden_upper_p90':(derived.selling_admin_to_revenue_pct,.9),
      'interest_burden_upper_p90':(derived.interest_to_revenue_pct,.9),
      'profit_change_lower_p10':(derived.prior_3y_signed_log_profit_change,.1)}
    return {key:float(values.dropna().quantile(q)) if values.notna().sum()>=10 else None for key,(values,q) in series.items()}

def evaluate_rules(company,features,benchmarks,model_flag):
    rows=[]
    def add(key,value,threshold,direction,reason,category):
        v=number(value);t=number(threshold)
        triggered=None if v is None or t is None else bool(v>t if direction=='above' else v<t if direction=='below' else v==t)
        rows.append({'rule':key,'value':v,'threshold':t,'triggered':triggered,'reason':reason,'category':category})
    add('three_prior_observed_consecutive_loss_years',features.get('prior_3y_loss_share'),1,'equal',
        'The three preceding observed years were losses. Three years is a study setting, not an HMRC cutoff; current profitability and commercial context still matter.','profitability')
    add('net_margin_below_training_industry_p10',None if number(company.get('revenue'))==0 else company.get('net_margin_pct'),benchmarks.get('net_margin_lower_p10'),'below',
        'Net margin below the training industry lower decile; functional and commercial explanations still needed.','profitability')
    leverage=number(company.get('liabilities_to_equity'))
    add('positive_leverage_above_training_industry_p90',leverage if leverage is not None and leverage>0 else None,benchmarks.get('positive_leverage_upper_p90'),'above',
        'Reported liabilities/equity exceeds positive training-peer upper decile. Liabilities are not necessarily borrowing or related-party debt.','financing_context')
    add('selling_admin_burden_above_training_industry_p90',features.get('selling_admin_to_revenue_pct'),benchmarks.get('selling_admin_burden_upper_p90'),'above',
        'Reported selling/administrative expense burden exceeds training peers; transaction counterparties remain unknown.','expense_context')
    add('interest_burden_above_training_industry_p90',features.get('interest_to_revenue_pct'),benchmarks.get('interest_burden_upper_p90'),'above',
        'Reported interest/revenue exceeds training peers; loan terms and lender context are not inferred.','financing_context')
    add('earnings_plus_interest_proxy_below_interest_charge',features.get('pretax_plus_interest_to_interest_proxy'),1,'below',
        'Pretax profit plus reported interest is below reported interest. This is a proxy, not verified operating cash-flow coverage or an HMRC cutoff.','financing_context')
    add('profit_trend_below_training_industry_p10',features.get('prior_3y_signed_log_profit_change'),benchmarks.get('profit_change_lower_p10'),'below',
        'Signed-log net-profit change over the three preceding years falls below the training-peer lower decile.','profitability')
    revenue=number(company.get('revenue'));profit=number(company.get('net_profit'))
    zero_loss=None if revenue is None or profit is None else bool(revenue==0 and profit<0)
    rows.append({'rule':'zero_revenue_with_reported_loss','value':profit,'threshold':0,'triggered':zero_loss,
        'reason':'Zero revenue and a net loss are preserved; commercial activity and loss explanation need review.','category':'activity_context'})
    amounts=[number(company.get(k)) for k in ['primary_revenue','cost_of_sales','gross_profit']]
    source_issue=None if any(v is None for v in amounts) else abs(amounts[0]-amounts[1]-amounts[2])>.05
    triggers=[r['rule'] for r in rows if r['triggered'] is True]
    route='SOURCE_DATA_REVIEW' if source_issue else 'MODEL_AND_INDICATOR_REVIEW' if model_flag and triggers else 'MODEL_REVIEW' if model_flag else 'INDICATOR_REVIEW' if triggers else 'NO_CURRENT_FINANCIAL_TRIGGER'
    return {'version':VERSION,'financial_review_route':route,'model_financial_flag':bool(model_flag),'indicator_triggers':triggers,
      'indicator_count':len(triggers),'unassessable_rules':[r['rule'] for r in rows if r['triggered'] is None],
      'source_gross_profit_review':source_issue,'rules':rows,'tp_compliance':'NOT_DETERMINED',
      'scope':'Observable financial review only. Peer thresholds and three-year settings are experimental, not HMRC legal rules.'}
