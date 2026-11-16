"""Local V1: enter any company, apply supported frozen models, explain review rules."""
from pathlib import Path
import sys,json,hashlib,re
import numpy as np
import pandas as pd
import joblib
import streamlit as st

APP=Path(__file__).resolve().parent
BASE=APP.parent
sys.path.insert(0,str(APP))
sys.path.insert(0,str(BASE))
from model_engine import screen_new_company,RATIO_FEATURES
from review_rules import QUESTIONS,OPTIONS,LABELS,FUNCTIONAL_PROFILES,VALUE_CHAIN_FUNCTIONS,RISK_RESPONSIBILITIES,profile_questions,assess_review,comparison_scope

st.set_page_config(page_title='Company review | V1',layout='wide')
TOKENS=json.loads((APP/'theme.json').read_text())
st.markdown('''<style>
.block-container{max-width:1240px;padding-top:2rem;padding-bottom:4rem}
h1,h2,h3{letter-spacing:-.02em} input,textarea{caret-color:var(--review-primary)}
:root{--review-primary:'''+TOKENS['primary']+''';--review-scroll:'''+TOKENS['scrollbar']+'''}
html,body,*{scrollbar-color:var(--review-scroll) transparent;scrollbar-width:thin}
::selection{background:'''+TOKENS['selection']+'''} textarea{resize:none} .stButton button{min-height:44px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>''',unsafe_allow_html=True)
CLEAN=BASE/'clean_data'
if not CLEAN.exists():CLEAN=BASE.parents[1]/'Downloads'/'Thai_Clean_Financial_Data'
MODEL=BASE/'outputs'/'thai_industry_models.joblib'
NAMES={'electronics_manufacturing':'Electronics manufacturing','electronics_trading':'Electronics trading','it_services':'IT services','printing_production':'Printing','professional_back_office':'Accounting / back office','road_freight':'Transport / logistics'}

@st.cache_resource
def load_model(path,modified):return joblib.load(path)

@st.cache_data
def load_data(path,modified):return pd.read_csv(path,dtype={'registration_number':str,'tsic_code':str})

def finite(value):
    try:value=float(value)
    except (ValueError,TypeError):return None
    return value if np.isfinite(value) else None

def safe_json(value):
    if isinstance(value,dict):return {str(k):safe_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe_json(v) for v in value]
    if isinstance(value,np.bool_):return bool(value)
    if isinstance(value,np.integer):return int(value)
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    return value

if not MODEL.exists() or not (CLEAN/'Column_dictionary.csv').exists() or not (BASE/'industry_scope.json').exists():
    st.error('Extract the whole reviewer package. Keep the saved model, dictionary and scope files together.')
    st.stop()
try:
    bundle=load_model(str(MODEL),MODEL.stat().st_mtime_ns)
    dictionary=pd.read_csv(CLEAN/'Column_dictionary.csv')
    descriptions=dict(zip(dictionary.english_column,dictionary.description))
    scope_metadata=json.loads((BASE/'industry_scope.json').read_text())
    represented={key:set(value) for key,value in scope_metadata['represented_tsic_codes'].items()}
except Exception:
    st.error('The reviewer resources could not be loaded. Extract the full package again.')
    st.stop()
def reset_review():
    for key in list(st.session_state):
        if key!='workspace':del st.session_state[key]
with st.sidebar:
    st.title('Company review')
    st.caption('Public reviewer edition · functional-profile screening')
    page=st.radio('Workspace',['Company screening'],key='workspace')
    st.button('Start a new review',on_click=reset_review)
    st.divider()
    st.write('**Model scope**')
    st.caption('Thai financial data · FY2021–FY2025 · six broad industry pools. Any company can be entered; unsupported pools or years receive an abstention.')
    st.markdown('[HMRC manual](https://www.gov.uk/hmrc-internal-manuals/international-manual/intm410000) · [Risk indicators](https://www.gov.uk/hmrc-internal-manuals/international-manual/intm482040)')
    st.markdown('[Read the screening logic](https://github.com/Witchayada-T/Transfer-pricing-preliminary-risk-indicator/blob/main/docs/SCREENING_LOGIC.md)')
    st.caption('Review concern is an experimental advisor workflow, not an HMRC score, Thai legal judgement or TP compliance conclusion.')
st.title('Transfer-pricing risk screening')
st.write('Assess financial warning signs and company-specific risk factors together. Results explain the review concern and missing information.')

st.subheader('1. Enter company details')
use_financial_model=st.checkbox('Include financial-model comparison',value=True)
if not use_financial_model:st.info('Rule-based screening can be completed without a financial-model comparison.')
mode=st.radio('Financial input',['Enter any new company','Upload company financial CSV'],horizontal=True)
source=pd.DataFrame();record={};history=[];year_default=2025
if mode=='Upload company financial CSV':
    upload=st.file_uploader('Wide financial CSV, including fiscal_year',type=['csv'])
    if upload:
        try:
            source=pd.read_csv(upload,dtype={'registration_number':str,'tsic_code':str})
            source=source.rename(columns=dict(zip(dictionary['column'],dictionary.english_column)))
            if 'registration_number' not in source:source['registration_number']='NEW_COMPANY'
            source['registration_number']=source.registration_number.fillna('NEW_COMPANY').astype(str)
            if 'fiscal_year' not in source:raise ValueError('The CSV needs a fiscal_year column.')
            source['fiscal_year']=pd.to_numeric(source.fiscal_year,errors='raise')
            if source.duplicated(['registration_number','fiscal_year']).any():raise ValueError('Each company and financial year must be unique.')
            chosen=st.selectbox('Uploaded company',source.registration_number.unique().tolist())
            source=source[source.registration_number.eq(chosen)].sort_values('fiscal_year')
            year_default=int(source.fiscal_year.max())
        except Exception as error:st.error(str(error));st.stop()
    else:st.info('Upload a CSV, or choose Enter any new company.');st.stop()
year=st.number_input('Financial year',min_value=1900,max_value=2100,value=year_default,step=1)
if len(source):
    current=source[source.fiscal_year.eq(year)]
    if len(current):record=current.iloc[0].to_dict()
    history=source[source.fiscal_year.lt(year)].to_dict('records')
prefix=mode+'_'+str(record.get('registration_number','new'))+'_'+str(year)
pool_options=['OTHER']+list(NAMES)
default_pool=record.get('nature_pool','OTHER')
pool=st.selectbox('Industry',pool_options,index=pool_options.index(default_pool) if default_pool in pool_options else 0,format_func=lambda value:'Other / not represented' if value=='OTHER' else NAMES[value],key=prefix+'_pool')
left,right=st.columns(2)
with left:
    name=st.text_input('Company name',value=str(record.get('company_name','')),key=prefix+'_name')
    registration=st.text_input('Registration number / identifier',value=str(record.get('registration_number','')),key=prefix+'_registration')
    tsic=st.text_input('TSIC code, if known',value=str(record.get('tsic_code','')),key=prefix+'_tsic')
    activity_label='Other industry / business description' if pool=='OTHER' else 'Business activity'
    activity=st.text_area(activity_label,value=str(record.get('tsic_activity','')),placeholder='Describe what this company actually does.',key=prefix+'_activity')
with right:
    role=st.selectbox('Operating role',['Unknown information','Manufacturer / producer','Distributor / trader','Service provider','Other — describe below'],key=prefix+'_role')
    functional_key=prefix+'_'+hashlib.sha256((registration.strip() or name.strip()).encode()).hexdigest()[:12]
    profile=st.selectbox('Primary functional profile',list(FUNCTIONAL_PROFILES),key=functional_key+'_profile_choice')
    st.caption(FUNCTIONAL_PROFILES[profile])
    group=st.text_area('Ownership, group and functional context',placeholder='Describe ownership and the functions, assets and risks.',key=prefix+'_group')
function_answers={};risk_responsibilities={}
with st.expander('Map functions across the value chain',expanded=False):
    st.caption('Yes means the entity performs or controls this function. Record the actual allocation across the full chain, including outsourced arrangements. A Yes here describes the business; it is not itself a risk indicator.')
    cols=st.columns(2)
    for i,(key,label) in enumerate(VALUE_CHAIN_FUNCTIONS):
        with cols[i%2]:function_answers[key]=st.selectbox(label,OPTIONS,key=functional_key+'_chain_'+key)
with st.expander('Record risk responsibilities',expanded=False):
    st.caption('Record actual control and risk bearing, not only the contract wording. Business risk bearing is different from transfer-pricing concern.')
    cols=st.columns(2)
    for i,(key,label) in enumerate(RISK_RESPONSIBILITIES):
        with cols[i%2]:risk_responsibilities[key]=st.selectbox(label,OPTIONS,key=functional_key+'_responsibility_'+key)
other_functions=st.text_area('Other functions or risk responsibilities (optional)',key=functional_key+'_other_functions')
scope=comparison_scope(pool,tsic,represented)
if use_financial_model and not scope['eligible']:st.info(scope['message']+' The independent rule-based assessment remains available.')

st.subheader('2. Add financial information')
inputs={**record,'company_name':name,'registration_number':registration,'fiscal_year':int(year),'nature_pool':pool,'tsic_code':tsic}
fields=['revenue','net_profit','primary_revenue','cost_of_sales','gross_profit','selling_and_administrative_expenses','profit_before_tax','interest_expense']
if use_financial_model:
    st.caption('THB amounts; reported percent/times ratios. Enter 5.2 for 5.2%, not 0.052. Leave unavailable values blank. Zero revenue and negative net profit are permitted.')
    cols=st.columns(2)
    for i,field in enumerate(fields[:2]):
        with cols[i]:inputs[field]=st.number_input(descriptions.get(field,field.replace('_',' ').title())+' (THB) *',value=finite(record.get(field)),format='%.2f',key=prefix+'_'+field)
    with st.expander('Reported ratios — complete the available financial inputs',expanded=mode=='Enter any new company'):
        cols=st.columns(3)
        for i,field in enumerate(RATIO_FEATURES):
            with cols[i%3]:inputs[field]=st.number_input(descriptions.get(field,field.replace('_',' ').title()),value=finite(record.get(field)),format='%.4f',help='Enter the reported percentage or times figure. Leave blank if unavailable.',key=prefix+'_'+field)
    with st.expander('Other income details and history',expanded=False):
        cols=st.columns(3)
        for i,field in enumerate(fields[2:]):
            with cols[i%3]:inputs[field]=st.number_input(descriptions.get(field,field.replace('_',' ').title())+' (THB)',value=finite(record.get(field)),format='%.2f',key=prefix+'_'+field)
        if mode=='Enter any new company' and year>2021:
            prior=pd.DataFrame([{'fiscal_year':past,'net_profit':np.nan} for past in range(max(2021,int(year)-4),int(year))])
            edited=st.data_editor(prior,hide_index=True,disabled=['fiscal_year'],column_config={'net_profit':st.column_config.NumberColumn('Net profit (THB)',format='%.2f')},width='stretch',key=prefix+'_history')
            history=[{'registration_number':registration,**row} for row in edited.to_dict('records')]
            st.caption('History is optional. Missing prior profits do not become No-loss answers.')
        elif history:st.dataframe(pd.DataFrame(history)[['fiscal_year','revenue','net_profit']],hide_index=True,width='stretch')
else:st.caption('Financial-model comparison is switched off. The functional-profile and risk-indicator rules remain available.')
inputs['history']=history

st.subheader('3. Record company-specific review facts')
st.caption('Any Yes to a risk indicator below raises Higher concern. Notes are optional. The rule-based assessment runs independently of the financial model.')
identity=(mode,registration.strip() or name.strip(),int(year))
previous_identity=st.session_state.get('review_case_identity')
if previous_identity is not None and previous_identity!=identity:
    for key in list(st.session_state):
        if key.startswith(prefix) and any(part in key for part in ['_criterion_','_related','_functional','_explained','_notes','_commercial']):del st.session_state[key]
    st.session_state.pop('last_report',None)
    st.info('Company or year changed. Additional review answers and the previous result were cleared. Check the financial inputs before evaluating.')
st.session_state['review_case_identity']=identity
answers={'functional_profile':profile}
st.write('**Background confirmations — Yes confirms context; it is not a risk flag.**')
cols=st.columns(3)
with cols[0]:answers['related_party_transactions']=st.selectbox('Related-party transactions are confirmed',OPTIONS,key=prefix+'_related')
with cols[1]:answers['functional_context_verified']=st.selectbox('Functions, assets and risks have been reviewed',OPTIONS,key=prefix+'_functional')
with cols[2]:answers['commercial_explanation_supported']=st.selectbox('Commercial explanation is supported by evidence',OPTIONS,key=prefix+'_explained')
with st.expander('Risk indicators — Yes raises Higher concern',expanded=True):
    for key,label,category,help_text in QUESTIONS:answers[key]=st.selectbox(label,OPTIONS,help=help_text,key=prefix+'_criterion_'+key)
with st.expander('Functional-profile risk indicators — Yes raises Higher concern',expanded=True):
    st.caption('The profile itself is neutral. These questions identify possible mismatches between the entity’s functions, risks and reward.')
    for key,label,category,help_text in profile_questions(profile):answers[key]=st.selectbox(label,OPTIONS,help=help_text,key=functional_key+'_'+profile+'_profile_criterion_'+key)
notes={'supporting_notes':st.text_area('Notes / references (optional)',key=prefix+'_notes'),
       'commercial_explanation':st.text_area('Commercial explanation for financial differences (optional)',key=prefix+'_commercial')}
details={'company_name':name,'registration_number':registration,'tsic_code':tsic,'industry_selection':'Other / not represented' if pool=='OTHER' else NAMES[pool],'industry_description':activity,'industry_and_activity':activity,'functional_role':role,'operating_role':role,'functional_profile':profile,'value_chain_functions':function_answers,'risk_responsibilities':risk_responsibilities,'other_functions':other_functions,'group_context':group,'nature_pool':pool,'fiscal_year':int(year),'financial_comparison_enabled':use_financial_model}
fingerprint=hashlib.sha256(json.dumps(safe_json({'inputs':inputs,'answers':answers,'notes':notes,'details':details}),sort_keys=True).encode()).hexdigest()
if st.button('Evaluate company',type='primary',width='stretch'):
    try:
        with st.spinner('Applying saved models and review rules…'):
            financial={'status':'ABSTAIN','financial_screening_flag':None,'tp_status':'NOT_DETERMINED','model_version':bundle['version'],'financial_model_display_status':'Not assessed'}
            if not use_financial_model:financial.update(reason='Financial-model comparison was not requested.',not_requested=True)
            elif not scope['eligible']:financial['reason']=scope['message']
            else:
                try:
                    for item in history:
                        value=item.get('net_profit')
                        if value is not None and not pd.isna(value) and finite(value) is None:raise ValueError('Prior annual net profit must be numeric or blank.')
                    financial=screen_new_company(inputs,bundle)
                except Exception as error:financial['reason']='Financial inputs need correction: '+str(error)
            review=assess_review(financial,answers,notes)
        st.session_state['last_report']={'fingerprint':fingerprint,'company_details':details,'financial_result':financial,'review_result':review,'analyst_answers':answers,'analyst_notes':notes}
    except Exception as error:st.error('Check the supplied information: '+str(error))
report=st.session_state.get('last_report')
if report and report['fingerprint']!=fingerprint:st.info('Inputs changed. Choose Evaluate company to refresh the result.')
elif report:
    financial=report['financial_result'];review=report['review_result']
    st.divider();st.subheader('4. Review the result and decision set')
    {'Higher concern':st.warning,'Less concern':st.success,'More information needed':st.info}[review['concern']]('**Rule-based screening: '+review['concern']+'**')
    st.write('**Rule-based risk concern identified:**','Yes' if review['screening_flag'] is True else 'No current rule-based concern' if review['screening_flag'] is False else 'More information needed')
    st.caption('This result comes from the risk-indicator answers. Financial-model findings are shown separately below.')
    for reason in review['reasons']:st.write(reason)
    for warning in review.get('consistency_warnings',[]):st.warning(warning)
    for warning in review.get('financial_context_warnings',[]):st.warning(warning)
    display_status='Scored' if financial['status']=='SCORED' else 'Not assessed'
    display_flag='Yes' if financial.get('financial_screening_flag') is True else 'No' if financial.get('financial_screening_flag') is False else 'Unknown information'
    st.write('**Financial model:**',display_status,' · **Financial pattern flag:**',display_flag)
    if financial['status']!='SCORED':st.write(financial.get('reason',''))
    else:
        if financial.get('financial_rules',{}).get('source_gross_profit_review'):st.warning('Source accounting review needed: reported gross-profit figures require an explanation. The saved source values and model scores have been preserved.')
        st.dataframe(pd.DataFrame(financial['models']).T.rename_axis('method'),width='stretch')
        st.caption('Method scores are not probabilities. Each industry uses its own calibration threshold. Cluster '+str(financial['cluster'])+' is a financial-pattern group, not a risk level.')
        with st.expander('Computed financial indicators',expanded=False):st.dataframe(pd.DataFrame(financial['financial_rules']['rules']),hide_index=True,width='stretch')
    with st.expander('Decision set: fired rule, reasons and missing information',expanded=True):
        st.write('**Primary functional profile:**',review['functional_profile'])
        st.write('**Applied rule:**',review['rule_id'].replace('_',' ').capitalize());st.caption('Audit reference: '+review['rule_id']);st.write(review['policy'])
        st.write('**Separate financial review topics:**',', '.join(value.replace('_',' ') for value in review['financial_indicator_categories']) or 'None identified')
        st.write('**Rule-based review topics:**',', '.join(value.replace('_',' ') for value in review['analyst_indicator_categories']) or 'None reported')
        question_names={**LABELS,'related_party_transactions':'Related-party transactions are confirmed','functional_context_verified':'Functions, assets and risks have been reviewed','commercial_explanation_supported':'Commercial explanation is supported by evidence','functional_profile':'Primary functional profile'}
        st.write('**Unknown criteria:**')
        if review['unknown_criteria']:
            for criterion in review['unknown_criteria']:st.write('• '+question_names.get(criterion,criterion.replace('_',' ')))
        else:st.write('None')
        st.caption('One Yes to an applicable risk indicator is sufficient to raise a rule-based concern. Notes are optional; this is a screening result, not a confirmed tax finding.')
    st.download_button('Download company review',json.dumps(safe_json(report),indent=2,ensure_ascii=False).encode('utf-8'),'company_review_v1.json','application/json')
    st.caption(review['scope'])
st.divider();st.caption('Local reviewer edition. Saved models are not refitted. No scraping, automatic external sharing or TP compliance verdict. Original collected-company tables are not included.')
