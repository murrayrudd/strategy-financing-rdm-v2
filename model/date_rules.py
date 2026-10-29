"""Keep trading-day and contractual payment-day calendars distinct."""
from pathlib import Path
from datetime import date,timedelta
import json
from functools import lru_cache
DATA=json.loads((Path(__file__).parent/'data/calendars.json').read_text())
DATA={k:frozenset(v) for k,v in DATA.items()}

def is_open(day,calendar,extra_closures=()):
    if not date(2026,1,1)<=day<=date(2036,12,31):raise ValueError('calendar coverage exceeded')
    if calendar not in ('FED_NY','US_EQUITY','STRE_PAY'):raise ValueError('unverified calendar')
    return day.weekday()<5 and str(day) not in DATA[calendar] and day not in extra_closures

@lru_cache(maxsize=30000)
def following(day,calendar,extra_closures=()):
    while not is_open(day,calendar,extra_closures):day+=timedelta(days=1)
    return day

@lru_cache(maxsize=30000)
def previous_trading(day,n=1,extra_closures=()):
    if n<1:raise ValueError('positive trading-day offset')
    while n:
        day-=timedelta(days=1)
        if is_open(day,'US_EQUITY',extra_closures):n-=1
    return day

def strf_deferred_date(nominal):
    # Strictly ONE trading day after the 60th calendar day, then Fed NY roll.
    d=nominal+timedelta(days=61)
    d=following(d,'US_EQUITY')
    return following(d,'FED_NY')

def authorized_shares(events,instrument,effective_date,information_cutoff):
    available=[e for e in events if e['instrument']==instrument
               and e['effective_date']<=str(effective_date)
               and e['public_date']<=str(information_cutoff)]
    if not available:raise ValueError('no authorization known at information cutoff')
    return sorted(available,key=lambda e:(e['effective_date'],e['public_date']))[-1]['authorized']
