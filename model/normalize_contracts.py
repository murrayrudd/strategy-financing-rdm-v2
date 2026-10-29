"""Extract six make-whole tables directly from the packaged SEC indentures.

No network, no edits to source documents. Tables predating the August 2024
10-for-1 split are transformed in both price and share dimensions.
"""
import json,re
from pathlib import Path
from datetime import datetime
from decimal import Decimal as D
from lxml import html

ROOT=Path(__file__).resolve().parent

def run():
    manifest={x['id']:x for x in json.loads((ROOT/'data/source_manifest.json').read_text())}
    terms=json.loads((ROOT/'data/debt_terms.json').read_text())
    tables={}
    for t in terms:
        src=manifest[t['source_id']];tree=html.fromstring((ROOT/src['packaged_path']).read_bytes())
        candidates=[]
        for i,tab in enumerate(tree.xpath('//table')):
            rows=[[ ' '.join(c.text_content().split()) for c in tr.xpath('./td|./th')] for tr in tab.xpath('./tr|./tbody/tr')]
            rows=[[c for c in row if c] for row in rows]
            if any(r and 'Effective' in r[0] and sum('$' in c for c in r)>5 for r in rows):candidates.append((i,rows))
        if len(candidates)!=1:raise ValueError((t['instrument'],'ambiguous make-whole table'))
        table_index,rows=candidates[0];header=next(r for r in rows if r and 'Effective' in r[0] and '$' in ''.join(r))
        split=D(10) if t['instrument'] in ('2030A','2031','2032') else D(1)
        prices=[D(x.replace('$','').replace(',',''))/split for x in header[1:]]
        values=[]
        for row in rows:
            if not row or not re.match(r'[A-Z][a-z]+ \d',row[0]):continue
            dt=datetime.strptime(row[0],'%B %d, %Y').date()
            vals=[D(x)*split for x in row[1:]]
            assert len(vals)==len(prices)
            values.append({'date':str(dt),'additional_shares_per_1000':[str(x) for x in vals]})
        text=' '.join(tree.text_content().split())
        capmatch=re.search(r'no event (?:shall|will) the Conversion Rate.{0,130}?(?:exceed |exceeds )([0-9.]+) shares',text)
        if not capmatch:raise ValueError('missing cap')
        cap=D(capmatch.group(1))*split
        tables[t['instrument']]={'source_id':t['source_id'],'url':src['url'],'html_table_index':table_index,
            'split_factor_applied':str(split),'prices':[str(x) for x in prices],'rows':values,
            'max_total_conversion_rate':str(cap),'interpolation':'bilinear, calendar-day weight between dates',
            'outside_price_range':'zero additional shares','outside_date_range':'reject',
            'scope':'make-whole event date/stock price must be independently supplied; call only affects called notes'}
        t.update(observation_trading_days=20,physical_settlement_business_days=2,
                 observation_settlement_business_days=2,partial_call_min_remaining_usd=90000000 if t['instrument']=='2030A' else 75000000,
                 call_price_strictly_greater=(t['instrument']=='2030B'),
                 special_event_status='Make-whole table normalized; physical/cash/combination mechanics implemented. New reference-property or non-split antidilution events require verified event inputs.',
                 make_whole_file='make_whole_tables.json')
    (ROOT/'data/make_whole_tables.json').write_text(json.dumps(tables,indent=2))
    (ROOT/'data/debt_terms.json').write_text(json.dumps(terms,indent=2))
    print('Normalized',len(tables),'tables;',sum(len(v['rows'])*len(v['prices']) for v in tables.values()),'numeric cells')

if __name__=='__main__':run()
