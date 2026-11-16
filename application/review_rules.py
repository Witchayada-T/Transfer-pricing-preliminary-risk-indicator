"""Transparent V1 review-routing policy, separate from fitted financial scores.

This policy is an experimental advisor workflow, not HMRC numerical guidance,
Thai law, a probability of incorrect pricing, or a validated compliance label.
"""
OPTIONS = ('Unknown information', 'Yes', 'No')
QUESTIONS = [
    ('profit_activity_mismatch', 'Profit or loss appears inconsistent with business activity or group results', 'profitability', 'Explain the relevant functions, assets, risks and group comparison; a peer difference alone is insufficient.'),
    ('intangibles_low_reward', 'Intangibles or R&D are provided with no/low royalty or entrepreneurial reward', 'intangibles', 'Identify the intangible, owner, functions performed, counterparties and actual contractual reward.'),
    ('disproportionate_borrowing', 'Borrowing appears disproportionately high relative to shareholder funds', 'financing', 'Use borrowing and lender details; total liabilities are not the same as related-party debt.'),
    ('interest_service_concern', 'Interest appears high relative to the ability to service the debt', 'financing', 'Check loan terms and sustainable operating earnings/cash flow; a financial proxy is not verified coverage.'),
    ('noncommercial_transactions', 'Transactions appear to lack a commercial rationale', 'commercial_rationale', 'Describe the transaction, commercial alternatives and evidence for the concern.'),
    ('low_tax_related_party', 'Transactions occur with related parties in low-tax territories', 'counterparty_context', 'Identify the related party, jurisdiction, transaction amounts and applicable tax treatment.'),
    ('private_equity_debt', 'A private-equity acquisition relies on heavy debt funding', 'financing', 'Provide the acquisition and funding structure; ownership cannot be inferred from ratios.'),
    ('restructuring_reward_change', 'Restructuring, activity transfer or reward changes may warrant review', 'restructuring', 'Describe what changed in the functions, assets, risks, contracts and company reward.'),
    ('stock_decline', 'A disappearance or significant decline in stock may warrant review', 'operations', 'Provide inventory levels and operational explanation. Turnover ratios alone do not establish a stock decline.'),
]
LABELS={key:label for key,label,_,_ in QUESTIONS}
FUNCTIONAL_PROFILES={
    'Unknown information':'Select the primary functional profile; business activities and risk responsibilities are recorded separately.',
    'Risk-taking entity':'Entrepreneurial or principal role: controls important business risks and has the financial capacity to bear them. Review functions across the full value chain; outsourced activities do not automatically mean risks are outsourced.',
    'Routine entity':'Performs defined functions with limited assets and controlled business risks, such as routine manufacturing, distribution or support services. The profile does not guarantee a particular return or exclude losses.',
    'Market-facing entity':'Interacts with customers or develops the market through selling, distribution, marketing or customer relationships. This role can overlap with a risk-taking or routine role.'}
VALUE_CHAIN_FUNCTIONS=[('strategy','Business strategy and decision-making'),('research','Research and product development'),
    ('intangibles','Brand, technology and intellectual-property management'),('procurement','Procurement and sourcing'),
    ('production','Manufacturing or service delivery'),('quality','Quality control and product responsibility'),
    ('logistics','Warehousing, logistics and inventory management'),('marketing','Marketing and market development'),
    ('sales','Sales, pricing and customer contracts'),('customer_service','Customer relationships and after-sales service'),
    ('financing','Funding, treasury and financing'),('support','Administration and business support')]
RISK_RESPONSIBILITIES=[('market','Controls and bears market / demand risk'),('inventory','Controls and bears inventory / obsolescence risk'),
    ('credit','Controls and bears customer credit risk'),('product','Controls and bears product / service liability risk'),
    ('development','Controls and bears development / technology risk'),('capacity','Controls and bears production / capacity risk'),
    ('currency','Controls and bears foreign-exchange risk'),('funding','Controls and bears financing / liquidity risk')]
COMMON_PROFILE_QUESTIONS=[
    ('profile_reward_mismatch',"The company's reward appears inconsistent with its functional profile",'functional_alignment','Consider the functions performed, assets used and risks actually controlled. Yes raises a screening concern; notes are optional.'),
    ('unrewarded_value_chain','Important value-chain functions, assets or risks are not appropriately rewarded','functional_alignment','Review the functions and risks recorded for the entity. A business function being performed is not itself a risk indicator.')]
SPECIFIC_PROFILE_QUESTIONS={
    'Risk-taking entity':[('risk_taker_low_reward','The risk-taking entity controls important risks or intangibles without an appropriate reward','functional_alignment','Review risk control, financial capacity and the reward for entrepreneurial or intangible-related contributions.')],
    'Routine entity':[('routine_unexplained_losses','The routine entity has recurring losses without a business explanation','profitability','Losses may have legitimate causes. Select Yes only when recurring losses remain inconsistent with the declared routine role.')],
    'Market-facing entity':[('market_unrewarded_activity','Local marketing or customer-market functions are not appropriately rewarded','functional_alignment','Consider market development, customer relationships and local contributions; the market-facing role is not itself a concern.')]
}
for _questions in [COMMON_PROFILE_QUESTIONS,*SPECIFIC_PROFILE_QUESTIONS.values()]:
    LABELS.update({key:label for key,label,_,_ in _questions})

def profile_questions(profile):
    if profile not in FUNCTIONAL_PROFILES:raise ValueError('Select a supported primary functional profile.')
    return COMMON_PROFILE_QUESTIONS+SPECIFIC_PROFILE_QUESTIONS.get(profile,[])

def comparison_scope(pool,tsic,represented):
    code=str(tsic or '').strip()
    if code.endswith('.0') and code[:-2].isdigit():code=code[:-2]
    eligible=pool in represented and (not code or code in represented[pool])
    return {'eligible':eligible,'display_status':'Scored when inputs are sufficient' if eligible else 'Not assessed',
            'message':'' if eligible else 'This company cannot be compared with the current peer pool.'}

def normalize(value):
    if value is True:return 'Yes'
    if value is False:return 'No'
    if value is None:return 'Unknown information'
    text=str(value).strip().casefold()
    if text=='yes':return 'Yes'
    if text=='no':return 'No'
    if text in {'unknown','unknown information','','none','nan'}:return 'Unknown information'
    raise ValueError('Answers must be Yes, No, or Unknown information.')

def financial_categories(result):
    categories=set()
    for row in result.get('financial_rules',{}).get('rules',[]):
        if row.get('triggered') is not True:continue
        category=row.get('category','')
        categories.add({'profitability':'profitability','financing_context':'financing','expense_context':'operations','activity_context':'operations'}.get(category,'financial_pattern'))
    if result.get('financial_screening_flag'):
        feature=result.get('largest_masked_error_feature','')
        if any(word in feature for word in ['profit','margin','loss','revenue']):categories.add('profitability')
        elif any(word in feature for word in ['interest','liabilit','equity']):categories.add('financing')
        else:categories.add('operations')
    return categories

def assess_company_rules(answers,notes=None):
    """Independent rule assessment: no financial model or score is accepted."""
    notes=notes or {}
    profile=answers.get('functional_profile') or 'Unknown information'
    definitions=QUESTIONS+profile_questions(profile)
    supplied={key:normalize(answers.get(key)) for key,_,_,_ in definitions}
    related=normalize(answers.get('related_party_transactions'))
    functional=normalize(answers.get('functional_context_verified'))
    positives=[key for key,value in supplied.items() if value=='Yes']
    unknown=[key for key,value in supplied.items() if value=='Unknown information']
    unknown+=([key for key,value in [('related_party_transactions',related),('functional_context_verified',functional)] if value=='Unknown information'])
    if profile=='Unknown information':unknown.append('functional_profile')
    manual_categories={category for key,_,category,_ in definitions if supplied[key]=='Yes'}
    result={'version':'review-routing-v2-functional-profiles','concern':'More information needed','rule_id':'INSUFFICIENT_CONTEXT',
        'reasons':[],'positive_analyst_indicators':positives,'unknown_criteria':unknown,
        'screening_flag':None,'functional_profile':profile,'notes_provided':bool(str(notes.get('supporting_notes','')).strip()),
        'consistency_warnings':[],
        'analyst_indicator_categories':sorted(manual_categories),
        'tp_compliance':'NOT_DETERMINED','scope':'Independent rule-based review concern, not a TP violation, legal determination or calibrated probability. Financial-model results are separate supporting information.',
        'policy':'Any Yes to an applicable risk-indicator question raises Higher concern. Notes are optional. Functional profiles, value-chain activities and background confirmations are not risk triggers by themselves. Financial scores remain separate. This is a study screening policy, not an HMRC cutoff.'}
    if related=='No' and supplied['low_tax_related_party']=='Yes':
        result['consistency_warnings'].append('Related-party transactions are marked No, but low-tax related-party transactions are marked Yes. Reconcile the answers; the reported risk indicator remains raised.')
    # Positive reported risk indicators are not hidden by missing notes, unknown
    # context, an unsupported industry, or the absence of a model anomaly.
    if positives:
        result.update(concern='Higher concern',rule_id='YES_RISK_INDICATOR',screening_flag=True)
        result['reasons']=['At least one risk indicator was answered Yes. Closer transfer-pricing review is recommended.']
        result['reasons']+=['Risk indicator: '+LABELS[key]+'.' for key in positives]
        if unknown:result['reasons'].append('Other facts remain unknown; they do not cancel the identified screening concern.')
        result['reasons']+=result['consistency_warnings']
        return result
    if related=='Unknown information' or functional!='Yes' or profile=='Unknown information':
        result['reasons']=['Confirm the transaction context, select a primary functional profile and review functions, assets and risks before assigning lower concern.']
        return result
    if unknown:
        result['reasons']=['Answer the remaining criteria before assigning lower concern. Unknown information is not a negative answer.'];return result
    result['concern']='Less concern';result['rule_id']='NO_CURRENT_REVIEW_TRIGGER';result['screening_flag']=False
    result['reasons']=['All applicable rule-based risk indicators were answered No and the functional context was confirmed. No concern was raised by this rule set. Financial-model findings must be considered separately. This is not a compliance clearance.']
    return result


def assess_review(financial_result,answers,notes=None):
    """Keep the independent rule result beside, rather than gated by, the model."""
    result=assess_company_rules(answers,notes)
    result['financial_model_flag']=financial_result.get('financial_screening_flag')
    result['financial_indicator_categories']=sorted(financial_categories(financial_result))
    warnings=[]
    if financial_result.get('status')!='SCORED' and not financial_result.get('not_requested'):warnings.append('Financial comparison: Not assessed. '+financial_result.get('reason','Financial inputs are incomplete.'))
    elif result['financial_indicator_categories']:warnings.append('Separate financial warning signs are present. Review the model findings alongside the rule-based result.')
    if financial_result.get('financial_rules',{}).get('source_gross_profit_review'):warnings.append('Reported gross-profit figures require an accounting review. Source values and model scores are preserved.')
    result['financial_context_warnings']=warnings
    return result
