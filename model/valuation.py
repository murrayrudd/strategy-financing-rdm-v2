"""Paper 2, Appendix A2: zero-carry lognormal positive residual reference.

Not a forecast, risk-neutral price or fitted stochastic Bitcoin process.
Source: supplied Strategy financing under deep uncertainty, v11, pp. 5-6/A3.
"""
import math

def residual_reference(bitcoin_value, net_senior_claims, sigma=.65, years=3.):
    s,k=float(bitcoin_value),float(net_senior_claims)
    if s<0 or sigma<0 or years<0:raise ValueError('negative reference input')
    if k<=0:return s-k
    if not s or not sigma or not years:return max(0.,s-k)
    v=sigma*math.sqrt(years)
    d1=math.log(s/k)/v+v/2;d2=d1-v
    cdf=lambda z: .5*math.erfc(-z/math.sqrt(2))
    return max(0.,s*cdf(d1)-k*cdf(d2))
