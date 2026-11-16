"""Observable financial criteria; historical features never use future years."""
import numpy as np
import pandas as pd

CRITERIA_FEATURES=['prior_3y_loss_share','prior_loss_streak','prior_3y_signed_log_profit_change',
                   'selling_admin_to_revenue_pct','interest_to_revenue_pct','pretax_plus_interest_to_interest_proxy']

def criteria_features(data):
    out=pd.DataFrame(np.nan,index=data.index,columns=CRITERIA_FEATURES)
    def number(name):return pd.to_numeric(data.get(name,pd.Series(np.nan,index=data.index)),errors='coerce')
    revenue=number('revenue');interest=number('interest_expense');pretax=number('profit_before_tax')
    out['selling_admin_to_revenue_pct']=number('selling_and_administrative_expenses')/revenue.where(revenue>0)*100
    out['interest_to_revenue_pct']=interest.where(interest>=0)/revenue.where(revenue>0)*100
    out['pretax_plus_interest_to_interest_proxy']=(pretax+interest)/interest.where(interest>0)
    if all(name in data for name in ['registration_number','fiscal_year','net_profit']):
        frame=data[['registration_number','fiscal_year','net_profit']].copy()
        frame['fiscal_year']=pd.to_numeric(frame.fiscal_year,errors='coerce');frame['net_profit']=pd.to_numeric(frame.net_profit,errors='coerce')
        if frame.duplicated(['registration_number','fiscal_year']).any():raise ValueError('History must contain unique company/year records')
        for _,group in frame.groupby('registration_number'):
            profits=dict(zip(group.fiscal_year,group.net_profit))
            for index,row in group.iterrows():
                if pd.isna(row.fiscal_year):continue
                year=int(row.fiscal_year);window=[profits.get(y,np.nan) for y in range(year-3,year)]
                if year<2024 or not np.isfinite(window).all():continue
                out.loc[index,'prior_3y_loss_share']=float(np.mean(np.array(window)<0))
                streak=0
                for past in range(year-1,2020,-1):
                    if past not in profits or not np.isfinite(profits[past]) or profits[past]>=0:break
                    streak+=1
                out.loc[index,'prior_loss_streak']=streak
                signed=np.sign(window)*np.log1p(np.abs(window))
                out.loc[index,'prior_3y_signed_log_profit_change']=(signed[-1]-signed[0])/2
    return out.replace([np.inf,-np.inf],np.nan)

def company_history_frame(company):
    """Use only earlier records for the same company; append the current year last."""
    history=company.get('history',[])
    if history is None:history=[]
    if not isinstance(history,list):raise ValueError('history must be a list of annual financial records')
    year=int(float(company['fiscal_year']));reg=str(company.get('registration_number') or 'NEW_COMPANY')
    records=[]
    for record in history:
        if not isinstance(record,dict):raise ValueError('Each history record must be a dictionary')
        if str(record.get('registration_number') or reg)!=reg:raise ValueError('History belongs to another company')
        past=float(record.get('fiscal_year',np.nan))
        if np.isfinite(past) and past.is_integer() and 2021<=past<year:
            records.append({**record,'registration_number':reg,'fiscal_year':int(past)})
    current={k:v for k,v in company.items() if k!='history'}
    records.append({**current,'registration_number':reg,'fiscal_year':year})
    return pd.DataFrame(records)
