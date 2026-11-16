"""Explicit sklearn pipelines with the audited feature order and scaling math."""
import warnings
import numpy as np
from sklearn.base import BaseEstimator,TransformerMixin,RegressorMixin,clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler,FunctionTransformer
from sklearn.neural_network import MLPRegressor
from sklearn.utils.validation import check_is_fitted

class FinancialFeatureBuilder(TransformerMixin,BaseEstimator):
    """Stateless, causal financial feature engineering; identifiers never pass through."""
    def fit(self,X,y=None):return self
    def transform(self,X):
        from model_engine import feature_frame
        return feature_frame(X)

class ObservedIQRScaler(RobustScaler):
    """Fit on observed training values, with the existing near-zero IQR guard."""
    def fit(self,X,y=None):
        super().fit(X,y)
        q1,q3=np.nanpercentile(np.asarray(X,dtype=float),[25,75],axis=0)
        self.scale_=np.where(q3-q1>1e-9,q3-q1,1)
        return self

def make_preprocessor(features):
    # RobustScaler ignores NaNs during fit. Its normalized center is zero, so
    # imputing zero AFTER scaling is exactly imputing the raw training median.
    # This preserves the observed-only IQR; imputing before fit would shrink
    # IQRs for the structurally missing prior-history features.
    numeric=Pipeline([
        ('robust_scaler',ObservedIQRScaler(quantile_range=(25,75))),
        ('median_in_scaled_space',SimpleImputer(strategy='constant',fill_value=0,keep_empty_features=True)),
        ('tail_compression',FunctionTransformer(np.arcsinh,validate=False)),
    ])
    columns=ColumnTransformer([('financial_numeric',numeric,list(features))],remainder='drop',verbose_feature_names_out=False)
    return Pipeline([('financial_features',FinancialFeatureBuilder()),('columns',columns)])

def make_model_pipeline(preprocessor,model):
    return Pipeline([('preprocessor',clone(preprocessor)),('model',model)])

def fit_neural(estimator,X,y,name='neural',**fit_params):
    """Training-only retry for numerical convergence; never sees evaluation data."""
    def message(item):return '\n'.join(line.rstrip() for line in str(item.message).splitlines())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always');estimator.fit(X,y,**fit_params)
    attempts=[]
    model=estimator.named_steps['model'] if isinstance(estimator,Pipeline) else estimator
    if isinstance(model,MLPRegressor) and caught:
        attempts=[{'model':name,'initial_solver':'lbfgs','warning':message(item),'action':'Retry Adam using training rows only'} for item in caught]
        params={'solver':'adam','max_iter':5000,'tol':.0001,'n_iter_no_change':30}
        estimator.set_params(**{('model__'+key if isinstance(estimator,Pipeline) else key):value for key,value in params.items()})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always');estimator.fit(X,y,**fit_params)
    unresolved=[{'model':name,'warning':message(item)} for item in caught]
    return estimator,unresolved,attempts

class MaskedReconstructionRegressor(RegressorMixin,BaseEstimator):
    """One network per held-out feature; observed_mask excludes imputed targets."""
    def __init__(self,feature_names=None,random_state=20261111):
        self.feature_names=feature_names;self.random_state=random_state
    def fit(self,X,y=None,observed_mask=None):
        X=np.asarray(X,dtype=float)
        if observed_mask is None:raise ValueError('Pass model__observed_mask from observed training features; imputed targets must not be learned.')
        observed=np.asarray(observed_mask,dtype=bool)
        if observed.shape!=X.shape:raise ValueError('Observed-target mask must match transformed training features')
        self.n_features_in_=X.shape[1];self.estimators_=[];self.training_warnings_=[];self.optimization_attempts_=[]
        for j in range(X.shape[1]):
            target=observed[:,j]
            if not target.any():raise ValueError('No observed training targets for masked feature')
            model=MLPRegressor(hidden_layer_sizes=(8,),activation='tanh',solver='lbfgs',alpha=1,max_iter=3000,max_fun=100000,tol=.001,random_state=self.random_state+j)
            label='masked_'+(self.feature_names[j] if self.feature_names is not None else str(j))
            fitted,unresolved,attempts=fit_neural(model,np.delete(X[target],j,axis=1),X[target,j],label)
            self.estimators_.append(fitted);self.training_warnings_+=unresolved;self.optimization_attempts_+=attempts
        return self
    def predict(self,X):
        check_is_fitted(self,'estimators_');X=np.asarray(X,dtype=float)
        if X.shape[1]!=self.n_features_in_:raise ValueError('Financial feature count differs from fitted model')
        return np.column_stack([model.predict(np.delete(X,j,axis=1)) for j,model in enumerate(self.estimators_)])
