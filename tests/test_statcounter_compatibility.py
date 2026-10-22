import importlib.util
import json
from pathlib import Path
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / 'Mobile phone OS share' / 'statcounter_client.py'
spec = importlib.util.spec_from_file_location('statcounter_under_test', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_external_chart_endpoint_and_parser_are_preserved(monkeypatch):
    client = module.StatCounterClient('https://gs.statcounter.com/os-market-share/mobile-tablet-console/south-korea/')
    url = client._build_chart_url('2026-10')
    assert url.startswith('https://gs.statcounter.com/chart.php?os_combined-KR-monthly-202610-202610-bar')
    assert 'device_hidden=mobile%2Btablet%2Bconsole' in url
    payload = {'xml':'<chart><set label="Android" value="75"/><set label="iOS" value="25"/></chart>'}
    chart = 'var json = '+json.dumps(payload)+'; if (FusionCharts'
    monkeypatch.setattr(client, '_get_text', lambda target: chart if 'chart.php' in target else '')
    rows = client.fetch_month_records('2026-10', 'KR', 'StatCounter')
    assert [(r.vendor,r.share) for r in rows] == [('Android',75.0),('iOS',25.0)]


def test_chart_failure_still_uses_matching_month_snapshot(monkeypatch):
    client = module.StatCounterClient('https://gs.statcounter.com/example')
    html = '<table class="stats-snapshot"><tbody><tr><th>Android</th><td class="count">75</td></tr></tbody><tfoot><tr><td>October 2026</td></tr></tfoot></table>'
    def fetch(url):
        if 'chart.php' in url:
            raise module.requests.ConnectionError('offline')
        return html
    monkeypatch.setattr(client, '_get_text', fetch)
    assert client.fetch_month_records('2026-10','KR','StatCounter')[0].share == 75.0
