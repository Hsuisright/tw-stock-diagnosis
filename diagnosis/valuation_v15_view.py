"""V1.5 presentation; reuse approved source adapter and requirement functions."""
from pathlib import Path
import sqlite3
import pandas as pd
import streamlit as st
from .valuation_requirement_view import load, fingerprint
from .valuation_requirement import requirement, summary_table
from .eps_history_store import comparable_rows
from .eps_historical_capability import base_eps, required_growths, summaries

@st.cache_data(ttl=3600, max_entries=64)
def growth_data(eps_db, ticker, cutoff, signature):
    rows, events = comparable_rows(Path(eps_db), ticker, cutoff)
    return rows, events, *summaries(rows)


@st.cache_data(ttl=3600, max_entries=64)
def current_actual_ttm(eps_db, ticker, cutoff, signature):
    """Return the only V1.5 TTM EPS eligible for the valuation calculation.

    The value is exactly four continuous reported quarterly EPS observations
    with one EPS basis.  No price or PE input is accepted or consulted.
    """
    rows, events = comparable_rows(Path(eps_db), ticker, cutoff)
    actual = base_eps(rows, cutoff)
    return dict(
        value=actual["value"], components=actual["components"], reason=actual["reason"],
        eps_basis=(actual["components"][0]["eps_basis"] if actual["components"] and not actual["reason"] else None),
        basis_events=events,
    )

def percent(x):
    return 'N/A' if x is None else f'{x:.1%}'

def render(result, root, db, eps_db=None):
    st.markdown('[ⓘ 指標說明](?view=valuation_help)')
    st.subheader('市場要求 vs 歷史 EPS 成長')
    st.caption('目前價格要求的獲利成長速度，公司自己的歷史是否曾出現過？')
    try:
        history_path = Path(eps_db or root/'data/eps_history.sqlite3')
        signature = fingerprint(history_path)
        records, basis_events, capability, observations = growth_data(str(history_path), result['stock_id'], result['price_date'], signature)
        base = current_actual_ttm(str(history_path), result['stock_id'], result['price_date'], signature)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        st.info('資料不足（DATA GAP）：現有來源無法驗證，暫不計算。')
        return
    reference_pe = result.get('normal_pe')
    required_eps = result['price'] / reference_pe if isinstance(reference_pe, (int, float)) and reference_pe > 0 else None
    growth = required_growths(required_eps, base['value'])
    if base['reason'] or not records:
        st.info('資料不足（DATA GAP）：無法完整比較現價要求，保留 N/A。')
    else:
        st.info('以下為市場要求與歷史觀察對照，不代表公司未來能再次達成。')
    for col, label, value in zip(st.columns(3), ('近四季實際 EPS（TTM，元）','歷史參考本益比（倍）','市場隱含所需 EPS（元）'),
                                 (base['value'],reference_pe,required_eps)):
        col.metric(label, 'N/A' if value is None else f'{value:.2f}')
    rows = []
    for s in capability:
        g = (growth['one_year'] if s['years'] == 1 else growth['two_year'] if s['years'] == 2 else growth['three_year'])
        rows.append({'期間':f"{s['years']}年" + ('（年化）' if s['years']>1 else ''),
            '市場目前要求':percent(g),'歷史中位數':percent(s['median']),
            '歷史較高區間（P75）':percent(s['p75']),'歷史最高':percent(s['maximum']),'樣本數':s['n']})
    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    st.caption('歷史最高只是曾經觀察到的數字，不代表可再次做到。樣本按季度滾動、彼此重疊，並非獨立預測。')
    with st.expander('歷史 EPS 成長明細與資料資格'):
        st.caption('單季基本 EPS 組成四季合計；缺季不補值。起點或終點非正數不計 CAGR。使用目前版本資料，非嚴格 PIT。')
        st.write('現價資料日：'+result['price_date'])
        if base['reason']: st.write('缺失原因：'+base['reason'])
        st.caption('口徑：基本 EPS｜範圍：FinMind 綜合損益表（提供者未在逐筆回應附合併範圍欄位）｜資格：目前版本、非 PIT。')
        if basis_events:
            st.caption('已排除最近一次已知股數基準事件以前的季資料；原始資料仍保留。')
        st.dataframe(pd.DataFrame([{k:v for k,v in x.items() if k != 'source_lineage'} for x in observations]).rename(
            columns={'years':'年數','start':'起始季末','end':'終止季末','start_eps':'起始四季 EPS','end_eps':'終止四季 EPS','growth':'成長率'}),hide_index=True)
        st.json({'本次基準來源':base['components'],'歷史起終點來源':observations},expanded=False)
    with st.expander('查看歷史市場領先時間'):
        try:
            facts, episodes = load(str(root), str(db), result['stock_id'], result['price_date'],
                (fingerprint(root/'data/interpretation_sources/bundle.json'), fingerprint(db), fingerprint(Path(str(db)+'-wal'))))
            legacy_requirement = requirement(facts, result['stock_id'], result['price_date'], result['price'], result.get('normal_pe'))
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            st.info('資料不足（DATA GAP）：歷史市場領先時間的本機研究資料未部署，暫不計算。')
            return
        st.write('歷史價格曾先反映 EPS 要求後，實際獲利花多久才達成；不是預測本次需要多久。')
        table=pd.DataFrame(summary_table(episodes,legacy_requirement['bucket']))
        table['Status']=table['Status'].replace({'OK':'樣本數達最低要求','INSUFFICIENT SAMPLE':'樣本不足'})
        for c in ('≤6M','6–12M','1–2Y','>2Y','Not Fulfilled'): table[c]=table[c].astype(str)
        table=table.rename(columns={'EPS Requirement':'所需成長','≤6M':'6個月內','6–12M':'6～12個月','1–2Y':'1～2年','>2Y':'超過2年','Not Fulfilled':'尚未觀察到實現','N':'樣本數','Status':'資料狀態'})
        st.dataframe(table,hide_index=True)
        st.caption('→ 為目前需求組；少於5筆不呈現分布。已達成為0個月。未觀察到實現是右設限，不代表失敗。')
        st.warning('未還原價格與目前版本 EPS；以經濟季末計時，不是公告確認日。股本跨期可比性未全面驗證。歷史參考 PE 使用先前季度 Peak PE，與現價月末 PE 樣本不同。')
        display=[]
        statuses={'N/A':'資料不足','ALREADY_MET':'起點已達成','FULFILLED':'已達成','RIGHT_CENSORED':'尚未觀察到實現'}
        for x in episodes:
            display.append({'季度':x['quarter_end'],'最高收盤日':x['peak_date'],'所需 EPS':x['required_eps'],
                '狀態':statuses[x['status']],'達成季末':x['completion_date'],'經過天數':x['lead_days'],'追蹤截止':x['censor_date']})
        st.dataframe(pd.DataFrame(display),hide_index=True)

TOPICS = [
 ('本益比（PE）','價格相對每股盈餘的倍數。','價格 ÷ EPS。','估值倍數。','不是便宜或昂貴的保證。','股價100元、EPS5元，PE為20倍。'),
 ('歷史 PE 參考','歷史觀察倍數，不是合理 PE。','現價沿用五年月末正PE中位數；歷史領先時間沿用起點前至少四個完整季度 PeakClose/BaseEPS 的中位數。','價格要求的參考基準。','不是目標價；兩種參考樣本不同。','參考20倍、股價120元，需要EPS6元。'),
 ('前四季基準 EPS','觀察季度之前四個完整季度實際獲利合計。','Qn−1 至 Qn−4 單季基本 EPS 相加，不含 Qn。','比較獲利起點。','缺季不換舊窗口，不從Price/PE反推。','四季各1元，基準4元。'),
 ('市場隱含所需 EPS','以參考倍數換算價格要求。','股價 ÷ 歷史參考 PE。','價格需要多少獲利支持。','不是EPS預測。','股價120元、PE20倍，要求6元。'),
 ('1／2／3 年所需成長','同一EPS要求在不同年限下的年化速度。','(RequiredEPS / BaseEPS)^(1/n) − 1，n=1、2、3。','成長壓力。','不是公司會達成的時間；負值不是衰退預測。','基準4元、要求6元：1年50%、2年22.5%、3年14.5%。'),
 ('EPS 歷史成長能力','公司自己實際出現過的滾動成長觀察。','1年：TTM(t+4季)/TTM(t)−1；2／3年取8／12季終點再年化。P75用線性分位數。','中位數、較高區間、最高與樣本數。','最高不是產能上限或再次達成承諾；重疊觀察不是獨立樣本。','四季EPS由4元到6元，一年成長50%。'),
 ('年複合成長率（CAGR）','把多年變化換算成每年等效成長。','(終點 / 起點)^(1/年數) − 1。起點須正，負終點不計算。','讓1、2、3年可按年化速度比較。','不表示每年實際都如此成長。','4元兩年變9元，CAGR50%。'),
 ('市場領先時間','歷史價格要求到實際四季EPS達成的經過時間。','完整季度最高收盤、同價最早日；往後找首次達標實際EPS季末。起點已達標為0。','歷史實現節奏。','不是本次達成時間；不是公告日或交易回測。','起點要求6元，之後某季四季EPS首次6.2元即達成。'),
 ('尚未觀察到實現','追蹤截至資料末端仍未見達標，即右設限。','固定要求，追蹤至最後連續可驗證EPS季度；缺季停止。','哪些觀察還沒有結果。','不代表FAIL、永久無法達成或市場一定錯。','要求6元，截止只有5元，列尚未觀察到實現。'),
 ('反折分數（TRS）','既有技術證據綜合指標。','沿用原趨勢20、動能20、量價15、相對強弱15、結構20、型態10權重；不改公式。','價格反折證據與階段。','不是成功率、合理價或買賣建議。','70分不等於70%會上漲。'),
]

def render_help():
    st.title('V1.5 指標說明')
    st.markdown('[返回分析](?)')
    st.caption('中文索引：選擇要了解的指標；公式集中於此，不參與計算。')
    selected=st.selectbox('指標索引',[t[0] for t in TOPICS])
    topic=next(t for t in TOPICS if t[0]==selected)
    st.subheader(topic[0])
    for label,text in zip(('1. 這是什麼','2. 怎麼計算','3. 用來看什麼','4. 不能代表什麼','5. 簡單範例'),topic[1:]):
        st.markdown('**'+label+'**')
        st.write(text)
