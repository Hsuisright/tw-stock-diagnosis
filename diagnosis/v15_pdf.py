"""V1.5 presentation-only PDF. No database, network or analysis engine access."""
from dataclasses import asdict
from datetime import datetime, date
from hashlib import sha256
from io import BytesIO
import json
from math import isfinite
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

FONT_ROOT = Path(__file__).resolve().parents[1] / 'assets/v15_pdf_fonts'
FONT = 'V15ReportTC'


def _number(value, places=2):
    if value is None or isinstance(value, bool):
        return 'N/A' if value is None else ('是' if value else '否')
    try:
        return f'{float(value):.{places}f}' if isfinite(float(value)) else 'N/A'
    except (ValueError, TypeError):
        return 'N/A'


def page_payload(result, interpretation, figures):
    """Explicit public allowlist; unknown fields and private caller data stay out."""
    current = result.get('reversal')
    cutoff=result.get('price_date')
    if current and cutoff and current.date>cutoff:
        raise ValueError('反折資料日晚於行情截止日，停止匯出')
    rev = asdict(current) if current else {}
    allowed = ('date', 'score', 'stage', 'coverage', 'model_version', 'confirmation_price',
               'failure_price', 'setup_started', 'setup_id', 'rsi14', 'macd_histogram',
               'volume_ratio', 'relative_20d', 'relative_60d', 'obv_above_ma10',
               'structure', 'pattern', 'evidence', 'pending', 'warnings',
               'trend_score', 'momentum_score', 'volume_score', 'relative_score',
               'structure_score', 'pattern_score')
    t = result.get('technical')
    b = result.get('bollinger')
    out = {k: result.get(k) for k in ('stock_id', 'stock_name', 'price_date', 'price', 'price_label', 'trend_label')}
    out['schema_version']='v15-pdf-1'
    out['reversal'] = {k: rev.get(k) for k in allowed}
    out['technical_summary'] = getattr(t, 'summary', None)
    out['bollinger'] = {k: getattr(b, k, None) for k in ('percent_b', 'bandwidth', 'temperature')}
    out['interpretation'] = {k: interpretation.get(k) for k in ('overall', 'short_term', 'medium_term', 'long_term')}
    out['figures'] = []
    for fig in figures or []:
        traces = []
        for trace in fig.data:
            item = {'type': trace.type, 'name': trace.name, 'yaxis': trace.yaxis or 'y',
                    'orientation': getattr(trace, 'orientation', None)}
            for key in ('x', 'y', 'open', 'high', 'low', 'close'):
                values = getattr(trace, key, None)
                if values is not None:
                    item[key] = [str(v)[:10] if key == 'x' else
                                 (float(v) if v is not None and isfinite(float(v)) else None) for v in values]
            if cutoff:
                for value in item.get('x',[]):
                    if len(value)==10 and value[4]=='-' and value[7]=='-' and value>cutoff:
                        raise ValueError('頁面圖表含截止日之後的資料，停止匯出')
            if trace.type == 'scatter':
                item['mode'] = trace.mode
                item['line'] = {'color': trace.line.color}
            traces.append(item)
        out['figures'].append({'data': traces, 'layout': {
            'shapes': [{k:(str(s.to_plotly_json().get(k))[:10] if k in ('x0','x1') else s.to_plotly_json().get(k))
                       for k in ('type','yref','y0','y1','x0','x1')} for s in fig.layout.shapes]}})
    out['content_id'] = sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return out


def export_pdf(payload, generated_at=None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor
    manifest = json.loads((FONT_ROOT / 'provenance.json').read_text(encoding='utf-8'))
    for name in ('V16ReportTC-Regular.ttf', 'OFL.txt'):
        if sha256((FONT_ROOT / name).read_bytes()).hexdigest() != manifest[name]['sha256']:
            raise ValueError('PDF 字型或授權檔驗證失敗')
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(FONT_ROOT / 'V16ReportTC-Regular.ttf')))
    stamp = generated_at or datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=landscape(A4), invariant=1)
    W, H = landscape(A4)
    c.setTitle(f"V1.5 {payload['stock_id']} {payload['price_date']}")
    c.setAuthor('台股個股診斷 V1.5')
    c.setSubject('Page snapshot ' + payload['content_id'])
    ink = '#403A36'

    def text(value, x, y, size=10, color=ink):
        c.setFont(FONT, size); c.setFillColor(HexColor(color)); c.drawString(x, y, str(value))

    def para(value, x, top, width, size=9.2):
        p = Paragraph(escape(str(value or 'N/A')), ParagraphStyle('tc', fontName=FONT,
                      fontSize=size, leading=size*1.4, wordWrap='CJK', textColor=HexColor(ink)))
        _, height = p.wrap(width, 1000)
        p.drawOn(c, x, top-height)
        return height

    def heading(value, x, y):
        text(value, x, y, 11, '#875C50')

    def chart(figure, x, y, width, height, axis='y', fixed_range=None):
        # Consume Plotly's displayed numeric traces; only map to PDF coordinates.
        traces = [t for t in figure.get('data', []) if t.get('yaxis', 'y') == axis and t.get('orientation') != 'h']
        numeric = []
        for trace in traces:
            for key in ('low', 'high') if trace['type'] == 'candlestick' else ('y',):
                for v in trace.get(key, []):
                    if isinstance(v, (int, float)) and isfinite(v): numeric.append(v)
        if not numeric:
            text('N/A：圖表資料不足', x+15, y+height/2); return
        lo, hi = fixed_range or (min(numeric), max(numeric))
        span = hi-lo or 1
        dates = sorted(set(str(d)[:10] for t in traces for d in t.get('x', [])))
        index = {d: i for i, d in enumerate(dates)}
        left, bottom = x+42, y+25
        cw, ch = width-52, height-38
        fx = lambda d: left+index[str(d)[:10]]*cw/max(len(dates)-1, 1)
        fy = lambda v: bottom+(v-lo)/span*ch
        for n in range(4):
            v = lo+span*n/3
            c.setStrokeColor(HexColor('#DDD6CE')); c.setLineWidth(.4)
            c.line(left, fy(v), left+cw, fy(v))
            text(_number(v/1000000,1)+'M' if axis!='y' else _number(v,1), x, fy(v)-2, 7)
        colors = ('#875C50', '#427879', '#9D813E', '#655583', '#557583')
        for n, trace in enumerate(traces):
            typ = trace['type']; xs = trace.get('x', [])
            color = trace.get('line', {}).get('color') or colors[n % len(colors)]
            if not color.startswith('#'): color = colors[n % len(colors)]
            c.setStrokeColor(HexColor(color)); c.setFillColor(HexColor(color)); c.setLineWidth(.8)
            if typ == 'candlestick':
                for d, o, h, l, close in zip(xs, trace['open'], trace['high'], trace['low'], trace['close']):
                    c.setStrokeColor(HexColor('#B3574C' if close>=o else '#367965'))
                    c.setFillColor(HexColor('#B3574C' if close>=o else '#367965'))
                    xx = fx(d); c.line(xx, fy(l), xx, fy(h))
                    c.rect(xx-1.5, fy(min(o, close)), 3, max(abs(fy(close)-fy(o)), .6), fill=1, stroke=0)
            else:
                previous = None
                for d, v in zip(xs, trace.get('y', [])):
                    if v is None or not isinstance(v, (float, int)) or not isfinite(v):
                        previous = None; continue
                    xx, yy = fx(d), fy(v)
                    if typ == 'bar': c.line(xx, bottom, xx, yy)
                    elif trace.get('mode') == 'markers': c.circle(xx, yy, 2, fill=1, stroke=0)
                    elif previous: c.line(*previous, xx, yy)
                    previous = (xx, yy)
            text(trace.get('name') or 'TRS', x+42+(n%5)*88, y+height-5, 7, color)
        for shape in figure.get('layout', {}).get('shapes', []):
            if shape.get('type') == 'rect' and shape.get('yref','y')==axis:
                lower,upper=shape.get('y0'),shape.get('y1')
                if lower is not None and upper is not None:
                    first,last=shape.get('x0'),shape.get('x1')
                    xx0=fx(first) if first in index else left
                    xx1=fx(last) if last in index else left+cw
                    lower,upper=max(lower,lo),min(upper,hi)
                    if upper>=lower:
                        c.saveState(); c.setFillColor(HexColor('#A8C2B5')); c.setFillAlpha(.18)
                        c.rect(xx0,fy(lower),max(xx1-xx0,0),fy(upper)-fy(lower),fill=1,stroke=0)
                        c.restoreState()
            if shape.get('type') == 'line' and shape.get('yref', 'y') == axis:
                v = shape.get('y0')
                if v is not None and lo<=v<=hi:
                    c.setDash(3,2); c.setStrokeColor(HexColor('#786658'))
                    first = shape.get('x0'); last = shape.get('x1')
                    xx0=fx(first) if first in index else left
                    xx1=fx(last) if last in index else left+cw
                    c.line(xx0, fy(v), xx1, fy(v)); c.setDash()
        text(dates[0], left, y+7, 7); text(dates[-1], left+cw-60, y+7, 7)

    c.setFillColor(HexColor('#F7F2EA')); c.rect(0,0,W,H,fill=1,stroke=0)
    para(f"{payload.get('stock_name') or 'N/A'}（{payload['stock_id']}）｜V1.5 個股診斷",24,H-20,W-48,18)
    text(f"行情截止 {payload.get('price_date') or 'N/A'}  |  股價 {_number(payload.get('price'))} 元",24,H-66,11)
    r = payload['reversal']
    text(f"TRS {_number(r.get('score'),0)}/100  |  {r.get('stage') or 'N/A'}  |  確認價 {_number(r.get('confirmation_price'))}  |  失敗價 {_number(r.get('failure_price'))}",24,H-91,12)
    text(f"反折資料日 {r.get('date') or 'N/A'}  |  {r.get('model_version') or 'N/A'}  |  有效構面 {_number(r.get('coverage'),0)}/100",24,H-111,9)
    b = payload['bollinger']
    text(f"RSI14 {_number(r.get('rsi14'))}   MACD柱 {_number(r.get('macd_histogram'),4)}   量比 {_number(r.get('volume_ratio'))}   布林%B {_number(b.get('percent_b'))}   通道寬度 {_number(b.get('bandwidth'))}%",24,H-132,9)
    component = [('趨勢','trend_score',20),('動能','momentum_score',20),('量價','volume_score',15),('相對強弱','relative_score',15),('結構','structure_score',20),('型態','pattern_score',10)]
    text('   '.join(f'{label} {_number(r.get(key),0)}/{weight}' for label,key,weight in component),24,H-151,9)
    relative=lambda v:'N/A' if v is None else f'{v:+.1%}'
    text(f"OBV高於MA10 {_number(r.get('obv_above_ma10'))}  |  RS20 {relative(r.get('relative_20d'))}  |  RS60 {relative(r.get('relative_60d'))}",24,H-167,8.5)
    heading('頁面 K 線／均線與成交量',24,416)
    figs = payload['figures']
    if figs:
        chart(figs[0],24,212,488,195)
        volume_axis=next((t['yaxis'] for t in figs[0]['data'] if t.get('name')=='成交量'),'y2')
        chart(figs[0],24,134,488,73,axis=volume_axis)
        chart(figs[1],24,57,488,72,fixed_range=(0,100))
    else: text('N/A：頁面尚無反折圖表',24,300)
    heading('現有 V1.5 判讀與證據',532,416)
    sections = [('技術摘要',payload['technical_summary']),('綜合判讀',payload['interpretation'].get('overall')),
                ('短期注意',payload['interpretation'].get('short_term')),
                ('反折依據','；'.join(r.get('evidence') or []) or 'N/A：未提供'),
                ('待確認','；'.join(r.get('pending') or []) or 'N/A：未提供')]
    top = 399; overflow = []
    for label, value in sections:
        full = f'{label}：{value or "N/A"}'
        p = Paragraph(escape(full), ParagraphStyle('measure',fontName=FONT,fontSize=9.2,leading=12.88,wordWrap='CJK'))
        _, needed = p.wrap(W-556,1000)
        if top-needed < 116: overflow.append(full); continue
        top -= para(full,532,top,W-556)+9
    warnings = list(r.get('warnings') or [])
    if r.get('date') != payload.get('price_date'): warnings.append('反折資料日期與股價日期不同，請核對更新。')
    cutoff = payload.get('price_date')
    if cutoff and (datetime.fromisoformat(stamp).date()-date.fromisoformat(cutoff)).days>4:
        warnings.append('資料可能過期；報告產生時間不代表行情已更新。')
    caution = '未還原除權息／分割；歷史逐日重算不代表當時保存的實盤紀錄。缺漏列 N/A；TRS 不是成功機率。'
    warning_text='；'.join(warnings+[caution])
    warning_para=Paragraph(escape(warning_text),ParagraphStyle('warning',fontName=FONT,fontSize=8.4,leading=11.76,wordWrap='CJK'))
    _,warning_height=warning_para.wrap(W-556,10000)
    if warning_height>62:
        overflow.append('資料警示：'+warning_text)
        warning_text='資料警示較長，完整內容請見續頁。'+caution
    para(warning_text,532,103,W-556,8.4)
    if overflow:
        text('完整判讀／警示另有續頁，請一併閱讀。',532,44,8)
    text(f"產生時間 {stamp}  |  資料沿用本頁分析，未重新抓取行情",24,34,8)
    text(f"內容 ID {payload['content_id']}",24,20,7)
    if overflow:
        c.showPage(); heading('V1.5 判讀續頁（完整文字）',24,H-30); top=H-52
        for full in overflow:
            p = Paragraph(escape(full),ParagraphStyle('appendix',fontName=FONT,fontSize=10,leading=14,wordWrap='CJK'))
            _, h=p.wrap(W-48,10000)
            if h>H-90: raise ValueError('判讀文字過長，請在網站查看完整內容')
            if top-h<42: c.showPage(); top=H-30
            top-=para(full,24,top,W-48,10)+12
    c.save()
    return output.getvalue()


def render_download(result, interpretation, figures):
    import streamlit as st
    try:
        if result.get('reversal') is not None and (not figures or len(figures)!=2):
            raise ValueError('頁面圖表模組版本尚未一致，請重新啟動候選服務後下載')
        payload = page_payload(result, interpretation, figures)
        cached = st.session_state.get('_v15_pdf')
        if not cached or cached[0] != payload['content_id']:
            cached = (payload['content_id'], export_pdf(payload))
            st.session_state['_v15_pdf'] = cached
        st.download_button('下載 V1.5 PDF', cached[1],
                           file_name=f"V15_{result['stock_id']}_{result['price_date']}.pdf",
                           mime='application/pdf', on_click='ignore', key='download_v15_pdf')
    except Exception as exc:
        # PDF failures never hide or replace the original V1.5 analysis.
        st.warning(f'PDF 暫時無法產生：{exc}')
