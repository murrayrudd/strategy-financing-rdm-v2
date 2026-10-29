"""Read archived SEC inline XBRL and preserve reported values and source contexts."""
from html.parser import HTMLParser
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib, json, re, shutil

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'corporate_audit'


class FilingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts, self.facts = {}, []
        self.context = None
        self.capture = None
        self.tag_capture = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag.endswith(':context'):
            self.context = {'id': a['id'], 'dimensions': {}}
        if self.context is not None and (tag.endswith(':instant') or tag.endswith(':startdate') or tag.endswith(':enddate')):
            self.tag_capture = [tag, [], None]
        if self.context is not None and tag.endswith(':explicitmember'):
            self.tag_capture = [tag, [], a.get('dimension')]
        if tag == 'ix:nonfraction':
            self.capture = [a, []]

    def handle_data(self, data):
        if self.tag_capture:
            self.tag_capture[1].append(data)
        if self.capture:
            self.capture[1].append(data)

    def handle_endtag(self, tag):
        if self.tag_capture and tag == self.tag_capture[0]:
            value = ''.join(self.tag_capture[1]).strip()
            if tag.endswith(':explicitmember'):
                self.context['dimensions'][self.tag_capture[2]] = value
            else:
                self.context[tag.split(':')[-1]] = value
            self.tag_capture = None
        if tag.endswith(':context') and self.context is not None:
            self.contexts[self.context['id']] = self.context
            self.context = None
        if tag == 'ix:nonfraction' and self.capture:
            a, parts = self.capture
            raw = ''.join(parts).strip()
            clean = re.sub(r'[,$%\s\u00a0()]', '', raw)
            if clean in ('—', '–', '-', ''): clean = '0'
            try:
                value = Decimal(clean) * (Decimal(10) ** int(a.get('scale', '0')))
                if a.get('sign') == '-' or ('(' in raw and ')' in raw): value = -abs(value)
                self.facts.append({'name':a.get('name'), 'context':a.get('contextref'),
                                   'value':str(value), 'unit':a.get('unitref'),
                                   'decimals':a.get('decimals'), 'display':raw})
            except InvalidOperation:
                pass
            self.capture = None


def parse(path):
    obj = FilingParser(); obj.feed(path.read_text(errors='replace')); return obj


def main():
    if (ROOT/'sources').exists():
        reports=json.loads((ROOT/'data/periodic_sources.json').read_text())
    else:
        registry = json.loads((ARCHIVE/'data/source_registry.json').read_text())
        reports = [r for r in registry if r.get('form') in ('10-Q','10-K') and
                   '2024-12-31' <= r.get('reportDate','') <= '2026-06-30']
    dst = ROOT/'data';dst.mkdir(parents=True, exist_ok=True)
    selected=[]
    for r in reports:
        p=ROOT/r['packaged_path'] if 'packaged_path' in r else ARCHIVE/r['local_path']; obj=parse(p)
        selected.append({k:r[k] for k in ['source_id','url','reportDate','filingDate','local_path']})
        if 'packaged_path' in r:selected[-1]['packaged_path']=r['packaged_path']
        (dst/(r['reportDate']+'_facts.json')).write_text(json.dumps({'contexts':obj.contexts,'facts':obj.facts,'source':selected[-1]},indent=2))
    (dst/'periodic_sources.json').write_text(json.dumps(selected,indent=2))
    print(json.dumps({'periods':[r['reportDate'] for r in reports]}))


if __name__=='__main__':main()
