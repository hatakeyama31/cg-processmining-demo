import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import random
import requests

st.set_page_config(
    page_title="NeXT Diagnostics – CG制作プロセス分析",
    page_icon="🎬", layout="wide",
    initial_sidebar_state="expanded"
)

NAVY  = "#1A2B45"; STEEL = "#3F7AB0"; PALE  = "#EBF3FA"
WARN  = "#C05A20"; GREEN = "#1A6B3C"; LGRAY = "#F3F5F8"; MGRAY = "#7A8A9A"
ACCENT= "#8E3B6B"  # クライアント差し戻し・重篤な例外用
CLR   = dict(NAVY=NAVY,STEEL=STEEL,PALE=PALE,WARN=WARN,GREEN=GREEN,MGRAY=MGRAY)

st.markdown(f"""<style>
  .main .block-container{{padding-top:1.5rem}}
  .kpi{{background:white;border-radius:10px;padding:1.1rem 1.4rem;
        border-left:4px solid {STEEL};box-shadow:0 1px 4px rgba(0,0,0,0.07)}}
  .kpi-w{{border-left-color:{WARN}}} .kpi-g{{border-left-color:{GREEN}}}
  .kpi-lbl{{font-size:11px;color:#7A8A9A;font-weight:600;letter-spacing:.05em;
            text-transform:uppercase;margin-bottom:4px}}
  .kpi-val{{font-size:30px;font-weight:700;color:{NAVY};line-height:1.1}}
  .kpi-sub{{font-size:11px;color:#AAB5C0;margin-top:3px}}
  .sec{{font-size:14px;font-weight:600;color:{NAVY};border-left:4px solid {STEEL};
        padding-left:10px;margin:16px 0 10px}}
  .subsec{{font-size:12px;font-weight:600;color:{MGRAY};margin:2px 0 8px 2px}}
  .ai-box{{background:{PALE};border-radius:10px;padding:1.4rem 1.6rem;
           border:1px solid #C0D4E8;line-height:1.8;font-size:14px}}
  .hint{{background:{LGRAY};border-radius:8px;padding:.9rem 1.2rem;
         color:#8A9AAA;font-size:13px}}
  .issue-card{{background:white;border-radius:10px;padding:1.0rem 1.2rem;
        border-top:3px solid {ACCENT};box-shadow:0 1px 4px rgba(0,0,0,0.07);height:100%}}
  .issue-title{{font-size:13px;font-weight:700;color:{NAVY};margin-bottom:6px}}
  .issue-body{{font-size:12.5px;color:#4A5A6A;line-height:1.65}}
  .issue-num{{font-size:22px;font-weight:700;color:{ACCENT};margin-right:4px}}
</style>""", unsafe_allow_html=True)

# ── PHASES（工程レベル・俯瞰） ─────────────────────────────
STAGES = ["要求仕様定義","モデリング","リギング","テクスチャリング",
          "レイアウト","アニメーション","ライティング","レンダリング","品質チェック"]
PLAN  = {"要求仕様定義":2,"モデリング":5,"リギング":3,"テクスチャリング":4,
         "レイアウト":3,"アニメーション":8,"ライティング":4,"レンダリング":2,"品質チェック":2}
REVRT = {"要求仕様定義":.10,"モデリング":.20,"リギング":.12,"テクスチャリング":.18,
         "レイアウト":.15,"アニメーション":.44,"ライティング":.29,"レンダリング":.16,"品質チェック":.22}

# ── TASK CONFIG（工程内・業務手順レベル） ─────────────────
# ShotGrid / Flow Production Trackingのタスク管理を想定：
#   各工程は「作業 → 内部レビュー → (承認 or 差し戻し)」を基本ユニットとし、
#   クライアントレビューが入る工程、上流工程の手戻りが波及して保留が発生する工程を区別する。
TASK_CONFIG = {
    "要求仕様定義":   dict(upstream=None,        client=False, client_label=None,       render=False, client_base=0.0),
    "モデリング":     dict(upstream=None,        client=True,  client_label="コンセプト確認", render=False, client_base=0.15),
    "リギング":       dict(upstream="モデリング", client=False, client_label=None,       render=False, client_base=0.0),
    "テクスチャリング": dict(upstream="モデリング", client=False, client_label=None,       render=False, client_base=0.0),
    "レイアウト":     dict(upstream=None,        client=True,  client_label="構図確認",   render=False, client_base=0.18),
    "アニメーション": dict(upstream="レイアウト", client=True,  client_label="芝居確認",   render=False, client_base=0.28),
    "ライティング":   dict(upstream=None,        client=False, client_label=None,       render=False, client_base=0.0),
    "レンダリング":   dict(upstream=None,        client=False, client_label=None,       render=True,  client_base=0.0),
    "品質チェック":   dict(upstream=None,        client=True,  client_label="最終承認",   render=False, client_base=0.10),
}

# ── DATA（工程レベル + タスクレベルの状態フラグを同時生成） ──
@st.cache_data
def generate_data():
    random.seed(42); np.random.seed(42)
    PROJS = [
        {"id":"P01","name":"PROJECT ALPHA","type":"TVアニメ","n":80},
        {"id":"P02","name":"PROJECT NOVA", "type":"劇場版",  "n":50},
        {"id":"P03","name":"PROJECT ECHO", "type":"OVA",    "n":40},
    ]
    ARTISTS = [f"Artist {c}" for c in "ABCDEFGH"]
    rows = []; sid = 1
    for pr in PROJS:
        base = datetime(2025,4,1)
        for _ in range(pr["n"]):
            cx  = random.choices(["低","中","高"], weights=[.3,.5,.2])[0]
            art = random.choice(ARTISTS)
            cur = base + timedelta(days=random.randint(0,90))
            prev_reworked = False  # 直前工程で内部差し戻しがあったか（保留判定に利用）
            for si,stg in enumerate(STAGES):
                cfg = TASK_CONFIG[stg]
                pd_= PLAN[stg]; m={"低":.7,"中":1.0,"高":1.5}[cx]
                act= max(1.0, pd_*m+np.random.normal(0,pd_*.28))

                # 内部差し戻し（既存ロジック踏襲）
                rev= 0
                if random.random()<REVRT[stg]:
                    rev= random.choices([1,2,3],weights=[.55,.3,.15])[0]
                    act+= rev*pd_*.55

                # 保留（上流工程の手戻り波及によるアセット待ち）
                hold=False; hold_days=0.0
                if cfg["upstream"] is not None:
                    hp = 0.55 if prev_reworked else 0.07
                    if random.random()<hp:
                        hold=True; hold_days=round(np.random.uniform(1.0,4.0),1)
                        act+=hold_days

                # クライアントレビュー差し戻し
                creject=False; cdays=0.0
                if cfg["client"]:
                    if random.random()<cfg["client_base"]:
                        creject=True
                        cdays=round(pd_*np.random.uniform(0.6,1.3),1)
                        act+=cdays

                # リギング特有：差し戻し要因の内訳（実際のパイプラインで頻出する3類型）
                #   ウェイト不良＝スキニング（ウェイトペイント）起因、補正シェイプ不足＝デフォーメーションの局所破綻、
                #   検証NG＝命名規則・参照エラー・パフォーマンス予算超過（自動チェックで検出）
                rework_cause = None
                if stg=="リギング" and rev>0:
                    rework_cause = random.choices(
                        ["ウェイト不良","補正シェイプ不足","検証NG"], weights=[.5,.3,.2])[0]

                # リギング特有：パブリッシュ後、アニメーション工程で使用中に不具合が発覚し
                # リギングまで差し戻される「逆流」パターン（実務でよく起きるが、通常は可視化されない）
                downstream_recall=False
                if stg=="リギング" and random.random()<0.09:
                    downstream_recall=True
                    act+=round(np.random.uniform(1.0,3.0),1)

                end= cur+timedelta(days=act)
                rows.append({"shot_id":f"CUT_{sid:04d}","project":pr["name"],
                    "type":pr["type"],"stage":stg,"stage_idx":si,"artist":art,
                    "complexity":cx,"planned":pd_,"actual":act,"revision":rev,
                    "delay":max(0.0,act-pd_),"is_late":act>pd_+.5,
                    "hold":hold,"hold_days":hold_days,
                    "client_review":cfg["client"],"client_reject":creject,"client_days":cdays,
                    "rework_cause":rework_cause,"downstream_recall":downstream_recall,
                    "start":cur,"end":end})
                cur=end
                prev_reworked = rev>0 or creject
            sid+=1
    return pd.DataFrame(rows)

df = generate_data()

# ── DFG NETWORK GRAPH（工程レベル・俯瞰） ─────────────────
def make_dfg(fdf, stages):
    ALL  = stages + ["承認完了"]
    top  = stages[:5]
    bot  = stages[5:]

    pos = {}
    for i,s in enumerate(top): pos[s] = (1.0+i*2.2, 1.8)
    for i,s in enumerate(bot):  pos[s] = (9.8-i*2.2, 0.2)
    pos["承認完了"] = (1.0, 0.2)

    ns = fdf.groupby("stage").agg(
        n   =("shot_id","nunique"),
        act =("actual","mean"),
        pln =("planned","mean"),
        rev =("revision",lambda x:(x>0).mean()),
    ).reset_index().set_index("stage")

    NW, NH = 0.92, 0.23

    fig = go.Figure()
    fig.update_layout(
        height=390, margin=dict(t=8,b=36,l=8,r=8),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(range=[-0.5,12.0],showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(range=[-0.85,2.65],showgrid=False,zeroline=False,showticklabels=False),
        showlegend=False,
        font=dict(family="Yu Gothic UI")
    )

    for i in range(len(ALL)-1):
        a,b = ALL[i],ALL[i+1]
        if a not in pos or b not in pos: continue
        ax,ay = pos[a]; bx,by = pos[b]
        n_c = int(ns.loc[a,"n"]) if a in ns.index else 50
        w   = max(1.5, min(5.0, n_c/20))

        if abs(ay-by)>0.3:
            sx_,sy_ = ax, ay-NH
            ex_,ey_ = bx, by+NH
        elif bx < ax:
            sx_,sy_ = ax-NW, ay
            ex_,ey_ = bx+NW, by
        else:
            sx_,sy_ = ax+NW, ay
            ex_,ey_ = bx-NW, by

        fig.add_annotation(x=ex_,y=ey_,ax=sx_,ay=sy_,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=1.2,arrowwidth=w,
            arrowcolor=STEEL,showarrow=True,text="")

        mx=(ax+bx)/2; my=(ay+by)/2+(0.18 if abs(ay-by)<0.3 else 0)
        if a in ns.index:
            fig.add_annotation(x=mx,y=my,
                text=f"{ns.loc[a,'act']:.1f}日",
                showarrow=False,font=dict(size=8,color=MGRAY),
                bgcolor="rgba(255,255,255,0.85)",borderpad=2)

    for s in stages:
        if s not in pos or s not in ns.index: continue
        if ns.loc[s,"rev"] < 0.13: continue
        x,y = pos[s]; r = ns.loc[s,"rev"]
        if y>1.0:
            path=f"M {x+NW} {y+NH} C {x+NW*2.2} {y+0.72} {x-NW*0.6} {y+0.72} {x-NW} {y+NH}"
            ly=y+0.60
        else:
            path=f"M {x+NW} {y-NH} C {x+NW*2.2} {y-0.72} {x-NW*0.6} {y-0.72} {x-NW} {y-NH}"
            ly=y-0.60
        fig.add_shape(type="path",path=path,
            line=dict(color=WARN,width=2,dash="dot"),layer="above")
        fig.add_annotation(x=x+0.1,y=ly,
            text=f"↩ {r:.0%}",showarrow=False,
            font=dict(size=9,color=WARN),bgcolor="rgba(255,255,255,0.88)",borderpad=2)

    for s in ALL:
        if s not in pos: continue
        x,y = pos[s]
        if s=="承認完了":
            fill=GREEN
        elif s in ns.index:
            pct=(ns.loc[s,"act"]-ns.loc[s,"pln"])/ns.loc[s,"pln"]
            fill=WARN if pct>0.30 else STEEL if pct>0.10 else NAVY
        else:
            fill=NAVY

        fig.add_shape(type="rect",
            x0=x-NW,y0=y-NH,x1=x+NW,y1=y+NH,
            fillcolor=fill,line=dict(color="white",width=1.5),layer="above")

        lbl = s if len(s)<=7 else s[:6]+"…"
        fig.add_annotation(x=x,y=y+0.07,text=f"<b>{lbl}</b>",
            showarrow=False,font=dict(size=10,color="white"))
        if s in ns.index:
            fig.add_annotation(x=x,y=y-0.09,
                text=f"n={int(ns.loc[s,'n'])} | {ns.loc[s,'act']:.1f}日",
                showarrow=False,font=dict(size=8,color="rgba(255,255,255,0.85)"))
        elif s=="承認完了":
            fig.add_annotation(x=x,y=y-0.09,text="完了",
                showarrow=False,font=dict(size=8,color="rgba(255,255,255,0.85)"))

    fig.add_annotation(x=0,y=-0.75,xref="x",yref="y",
        text="🟦 標準　🟠 ボトルネック（計画比+30%超）　🟩 完了　⤾ リビジョンループ（発生率）",
        showarrow=False,font=dict(size=9,color=MGRAY))

    return fig

# ── TASK-LEVEL DFG（工程内・業務手順のドリルダウン） ────────
def _draw_loop(fig, pos, src, dst, rate, label, color, side, depth, NW, NH):
    sx,sy = pos[src]; dx,dy = pos[dst]
    if side=="below":
        path=f"M {sx} {sy-NH} C {sx} {sy-NH-depth} {dx} {dy-NH-depth} {dx} {dy-NH}"
        ly = -NH-depth-0.17
        base_y = min(sy,dy)
    else:
        path=f"M {sx} {sy+NH} C {sx} {sy+NH+depth} {dx} {dy+NH+depth} {dx} {dy+NH}"
        ly = NH+depth+0.17
        base_y = max(sy,dy)
    fig.add_shape(type="path",path=path,
        line=dict(color=color,width=2,dash="dot"),layer="above")
    mx=(sx+dx)/2
    fig.add_annotation(x=mx, y=base_y+ly,
        text=f"↩ {label} {rate:.0%}",showarrow=False,
        font=dict(size=9,color=color),bgcolor="rgba(255,255,255,0.92)",borderpad=2)

def make_task_dfg(stage, sdf):
    cfg = TASK_CONFIG[stage]
    n = sdf["shot_id"].nunique()

    fig = go.Figure()
    NW, NH = 1.05, 0.30

    # ── リギング専用：実際のパイプライン手順に基づく詳細フロー ──
    if stage=="リギング":
        hold_rate = sdf["hold"].mean()
        hold_avg  = sdf.loc[sdf["hold"],"hold_days"].mean() if sdf["hold"].any() else 0.0
        weight_rate     = (sdf["rework_cause"]=="ウェイト不良").mean()
        corrective_rate = (sdf["rework_cause"]=="補正シェイプ不足").mean()
        validation_rate = (sdf["rework_cause"]=="検証NG").mean()
        recall_rate     = sdf["downstream_recall"].mean()

        nodes = ["保留\n(モデル確定待ち)","スケルトン配置","スキニング\n(ウェイトペイント)",
                 "コントロールリグ\n構築","デフォーメーション\nテスト","リグ検証\n(自動チェック)",
                 "パブリッシュ\n(アニメーターへ)"]
        stats = {
            "保留\n(モデル確定待ち)": f"発生率 {hold_rate:.0%} | 平均{hold_avg:.1f}日",
            "スケルトン配置": f"n={n} | ジョイント配置・階層構築",
            "スキニング\n(ウェイトペイント)": f"最重要工程 | ウェイト不良差し戻し {weight_rate:.0%}",
            "コントロールリグ\n構築": f"IK/FK・コントローラ実装 | 差し戻し {corrective_rate:.0%}",
            "デフォーメーション\nテスト": "ストレスポーズでの変形検証",
            "リグ検証\n(自動チェック)": f"命名・参照・性能チェック | NG {validation_rate:.0%}",
            "パブリッシュ\n(アニメーターへ)": f"引き渡し完了 | 事後差し戻し {recall_rate:.0%}",
        }
        loops = [
            dict(src="デフォーメーション\nテスト",dst="スキニング\n(ウェイトペイント)",
                 rate=weight_rate,label="差し戻し(ウェイト不良)",color=WARN,side="below",depth=0.55),
            dict(src="デフォーメーション\nテスト",dst="コントロールリグ\n構築",
                 rate=corrective_rate,label="差し戻し(補正シェイプ不足)",color=WARN,side="below",depth=0.95),
            dict(src="リグ検証\n(自動チェック)",dst="コントロールリグ\n構築",
                 rate=validation_rate,label="差し戻し(検証NG:命名/性能)",color=WARN,side="below",depth=0.55),
            dict(src="パブリッシュ\n(アニメーターへ)",dst="スキニング\n(ウェイトペイント)",
                 rate=recall_rate,label="アニメーション工程からの差し戻し(逆流)",
                 color=ACCENT,side="above",depth=0.85),
        ]

        k = len(nodes)
        xs = [1.2 + i*2.35 for i in range(k)]
        pos = {node:(xs[i],1.0) for i,node in enumerate(nodes)}

        fig.update_layout(
            height=430, margin=dict(t=8,b=8,l=8,r=8),
            paper_bgcolor="white", plot_bgcolor="white",
            xaxis=dict(range=[-0.3, xs[-1]+2.0],showgrid=False,zeroline=False,showticklabels=False),
            yaxis=dict(range=[-1.75,2.35],showgrid=False,zeroline=False,showticklabels=False),
            showlegend=False, font=dict(family="Yu Gothic UI")
        )

        for i in range(k-1):
            a,b = nodes[i], nodes[i+1]
            ax,ay = pos[a]; bx,by = pos[b]
            fig.add_annotation(x=bx-NW,y=by,ax=ax+NW,ay=ay,
                xref="x",yref="y",axref="x",ayref="y",
                arrowhead=2,arrowsize=1.2,arrowwidth=2.4,
                arrowcolor=STEEL,showarrow=True,text="")

        for lp in loops:
            _draw_loop(fig, pos, lp["src"], lp["dst"], lp["rate"], lp["label"],
                       lp["color"], lp["side"], lp["depth"], NW, NH)

        for node in nodes:
            x,y = pos[node]
            if "パブリッシュ" in node: fill=GREEN
            elif "保留" in node:       fill=MGRAY
            elif "スキニング" in node: fill=STEEL
            else:                      fill=NAVY
            fig.add_shape(type="rect",
                x0=x-NW,y0=y-NH,x1=x+NW,y1=y+NH,
                fillcolor=fill,line=dict(color="white",width=1.5),layer="above")
            fig.add_annotation(x=x,y=y+0.10,text=f"<b>{node}</b>",
                showarrow=False,font=dict(size=9.5,color="white"),align="center")
            fig.add_annotation(x=x,y=y-NH-0.16,text=stats.get(node,""),
                showarrow=False,font=dict(size=8.5,color=MGRAY),align="center")

        return fig

    if cfg["render"]:
        nodes = ["レンダリング実行","レンダーチェック","承認\n(次工程へ)"]
        err_rate = (sdf["revision"]>0).mean()
        stats = {
            "レンダリング実行": f"n={n} | 平均{sdf['planned'].mean():.1f}日想定",
            "レンダーチェック": f"エラー再実行率 {err_rate:.0%}",
            "承認\n(次工程へ)": "完了",
        }
        loops = [("レンダーチェック","レンダリング実行", err_rate, "NG: 再レンダリング")]
    else:
        nodes = []
        stats = {}
        if cfg["upstream"] is not None:
            hold_rate = sdf["hold"].mean()
            hold_avg  = sdf.loc[sdf["hold"],"hold_days"].mean() if sdf["hold"].any() else 0.0
            nodes.append("保留\n(上流アセット待ち)")
            stats["保留\n(上流アセット待ち)"] = f"発生率 {hold_rate:.0%} | 平均{hold_avg:.1f}日"

        nodes.append("作業")
        stats["作業"] = f"n={n} | 平均{sdf['planned'].mean():.1f}日想定"

        nodes.append("内部レビュー")
        int_rate = (sdf["revision"]>0).mean()
        stats["内部レビュー"] = f"差し戻し率 {int_rate:.0%}"

        loops = [("内部レビュー","作業", int_rate, "差し戻し(内部QC)")]

        if cfg["client"]:
            nodes.append(f"クライアントレビュー\n({cfg['client_label']})")
            c_rate = sdf["client_reject"].mean()
            stats[f"クライアントレビュー\n({cfg['client_label']})"] = f"差し戻し率 {c_rate:.0%}"
            loops.append((f"クライアントレビュー\n({cfg['client_label']})","作業", c_rate, "差し戻し(クライアント)"))

        nodes.append("承認\n(次工程へ)")
        stats["承認\n(次工程へ)"] = "完了"

    k = len(nodes)
    xs = [1.2 + i*2.6 for i in range(k)]
    pos = {node:(xs[i],1.0) for i,node in enumerate(nodes)}

    fig.update_layout(
        height=330, margin=dict(t=8,b=70,l=8,r=8),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(range=[-0.3, xs[-1]+1.6],showgrid=False,zeroline=False,showticklabels=False),
        yaxis=dict(range=[-0.55,1.85],showgrid=False,zeroline=False,showticklabels=False),
        showlegend=False, font=dict(family="Yu Gothic UI")
    )

    for i in range(k-1):
        a,b = nodes[i], nodes[i+1]
        ax,ay = pos[a]; bx,by = pos[b]
        fig.add_annotation(x=bx-NW,y=by,ax=ax+NW,ay=ay,
            xref="x",yref="y",axref="x",ayref="y",
            arrowhead=2,arrowsize=1.2,arrowwidth=2.4,
            arrowcolor=STEEL,showarrow=True,text="")

    for src,dst,rate,label in loops:
        sx,sy = pos[src]; dx,dy = pos[dst]
        is_client = "クライアント" in label
        color = ACCENT if is_client else WARN
        depth = 0.85 if is_client else 0.55
        path = f"M {sx} {sy-NH} C {sx} {sy-NH-depth} {dx} {dy-NH-depth} {dx} {dy-NH}"
        fig.add_shape(type="path",path=path,
            line=dict(color=color,width=2,dash="dot"),layer="above")
        mx = (sx+dx)/2
        fig.add_annotation(x=mx, y=sy-NH-depth-0.16,
            text=f"↩ {label} {rate:.0%}",showarrow=False,
            font=dict(size=9,color=color),bgcolor="rgba(255,255,255,0.9)",borderpad=2)

    for node in nodes:
        x,y = pos[node]
        if "承認" in node:
            fill = GREEN
        elif "保留" in node:
            fill = MGRAY
        elif "クライアント" in node:
            fill = ACCENT
        else:
            fill = NAVY
        fig.add_shape(type="rect",
            x0=x-NW,y0=y-NH,x1=x+NW,y1=y+NH,
            fillcolor=fill,line=dict(color="white",width=1.5),layer="above")
        fig.add_annotation(x=x,y=y+0.08,text=f"<b>{node}</b>",
            showarrow=False,font=dict(size=10,color="white"),align="center")
        fig.add_annotation(x=x,y=y-NH-0.16,text=stats.get(node,""),
            showarrow=False,font=dict(size=9,color=MGRAY),align="center")

    return fig

# ── SIDEBAR ───────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='font-size:22px;font-weight:700;color:{NAVY};'>"
                f"NeXT<span style='color:{STEEL};'> Diagnostics</span></div>",
                unsafe_allow_html=True)
    st.caption("CG制作プロセス分析 Demo v3.0")
    st.divider()
    projs = ["全プロジェクト"] + sorted(df["project"].unique())
    sel   = st.selectbox("プロジェクト選択", projs)
    st.divider()
    phase_sel = st.selectbox("業務手順ドリルダウン：工程選択", STAGES, index=2)
    st.divider()
    api_key = st.text_input("Claude API Key", type="password", placeholder="sk-ant-...")
    st.caption("AI分析機能の利用に必要です")

fdf = df if sel=="全プロジェクト" else df[df["project"]==sel]

# ── TITLE ─────────────────────────────────────────────
st.markdown("## 🎬 CG制作プロセス分析ダッシュボード")
st.caption(f"{sel}　｜　{fdf['shot_id'].nunique():,} ショット　｜　"
           f"工程: {' → '.join(STAGES[:4])} → …　｜　ShotGrid連携（デモデータ）")

# ── KPI ───────────────────────────────────────────────
shots     = fdf["shot_id"].nunique()
avg_delay = fdf.groupby("shot_id")["delay"].sum().mean()
total_rev = int(fdf["revision"].sum())
on_time   = (1-fdf.groupby("shot_id")["is_late"].any().mean())*100
hold_rate_all = fdf.loc[fdf["stage"].map(lambda s: TASK_CONFIG[s]["upstream"] is not None),"hold"].mean()

c1,c2,c3,c4,c5 = st.columns(5)
for col,lbl,val,sub,cls in [
    (c1,"分析ショット数",    f"{shots:,}",        "全工程のログを可視化",   ""),
    (c2,"平均遅延日数",       f"{avg_delay:.1f}日", "ショットあたり合計遅延","kpi-w" if avg_delay>3 else ""),
    (c3,"総リビジョン回数",  f"{total_rev:,}回",   "全工程・全ショット合計", "kpi-w"),
    (c4,"期限内完了率",       f"{on_time:.0f}%",    "全ショット・全工程",     "kpi-g" if on_time>=70 else "kpi-w"),
    (c5,"上流波及による保留率", f"{hold_rate_all:.0%}", "モデリング/レイアウト起点", "kpi-w" if hold_rate_all>0.15 else ""),
]:
    with col:
        st.markdown(f"<div class='kpi {cls}'><div class='kpi-lbl'>{lbl}</div>"
                    f"<div class='kpi-val'>{val}</div>"
                    f"<div class='kpi-sub'>{sub}</div></div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── DFG（俯瞰） + Bottleneck ───────────────────────────
r2l, r2r = st.columns([3,2])

with r2l:
    st.markdown("<div class='sec'>プロセスフロー（工程レベル・俯瞰マップ）</div>",
                unsafe_allow_html=True)
    fig_dfg = make_dfg(fdf, STAGES)
    st.plotly_chart(fig_dfg, use_container_width=True)

with r2r:
    st.markdown("<div class='sec'>工程別ボトルネック（計画比）</div>",
                unsafe_allow_html=True)
    ss = fdf.groupby("stage").agg(actual=("actual","mean"),planned=("planned","mean")).reset_index()
    ss = ss[ss["stage"].isin(STAGES)]
    ss["stage"] = pd.Categorical(ss["stage"],categories=STAGES,ordered=True)
    ss = ss.sort_values("stage",ascending=True)
    ss["pct"] = (ss["actual"]-ss["planned"])/ss["planned"]*100

    fig_b = go.Figure(go.Bar(
        y=ss["stage"], x=ss["pct"], orientation="h",
        marker_color=[WARN if v>0 else GREEN for v in ss["pct"]],
        text=[f"{v:+.0f}%" for v in ss["pct"]], textposition="outside",
        hovertemplate="<b>%{y}</b><br>計画比: %{x:+.1f}%<extra></extra>"
    ))
    fig_b.add_vline(x=0,line_color=NAVY,line_width=1.5)
    fig_b.update_layout(
        height=390,margin=dict(t=8,b=8,l=10,r=65),
        paper_bgcolor="white",plot_bgcolor="white",
        xaxis_title="計画比（%）",
        font=dict(family="Yu Gothic UI",size=11)
    )
    fig_b.update_xaxes(gridcolor="#EEF2F6")
    st.plotly_chart(fig_b, use_container_width=True)

# ── TASK-LEVEL DFG（工程内ドリルダウン） ────────────────
st.markdown(f"<div class='sec'>業務手順レベルのプロセスフロー（工程内ドリルダウン：{phase_sel}）</div>",
            unsafe_allow_html=True)
st.markdown("<div class='subsec'>ShotGrid等のタスク管理ツールを想定した粒度：作業 → 内部レビュー → "
            "（差し戻し／保留／クライアントレビュー）→ 承認 の実態フローを可視化</div>",
            unsafe_allow_html=True)
sdf_task = fdf[fdf["stage"]==phase_sel]
fig_task = make_task_dfg(phase_sel, sdf_task)
st.plotly_chart(fig_task, use_container_width=True)

if phase_sel=="リギング":
    st.markdown("<div class='subsec' style='margin-top:14px'>リギング特化インサイト："
                "実際のタスク管理ツールで検出できる3つの差し戻し要因＋通常は見えない「逆流」パターン</div>",
                unsafe_allow_html=True)
    rg = sdf_task
    w_rate = (rg["rework_cause"]=="ウェイト不良").mean()
    c_rate = (rg["rework_cause"]=="補正シェイプ不足").mean()
    v_rate = (rg["rework_cause"]=="検証NG").mean()
    r_rate = rg["downstream_recall"].mean()

    rg1,rg2,rg3,rg4 = st.columns(4)
    with rg1:
        st.markdown(f"""<div class='issue-card'>
            <div class='issue-title'>ウェイト不良</div>
            <div class='issue-body'>差し戻し率 <span class='issue-num'>{w_rate:.0%}</span><br>
            スキニング工程の品質ばらつきが最大の手戻り要因。ウェイトペイントの標準化・
            レビュー観点の明文化が効果的。</div></div>""", unsafe_allow_html=True)
    with rg2:
        st.markdown(f"""<div class='issue-card'>
            <div class='issue-title'>補正シェイプ不足</div>
            <div class='issue-body'>差し戻し率 <span class='issue-num'>{c_rate:.0%}</span><br>
            肘・膝・肩などの局所的な変形破綻。ストレスポーズでの
            早期検証が手戻り削減の鍵。</div></div>""", unsafe_allow_html=True)
    with rg3:
        st.markdown(f"""<div class='issue-card'>
            <div class='issue-title'>検証NG(命名/性能)</div>
            <div class='issue-body'>差し戻し率 <span class='issue-num'>{v_rate:.0%}</span><br>
            命名規則違反・参照エラー・パフォーマンス予算超過。
            自動チェックスクリプトで人手レビュー前に検出可能。</div></div>""", unsafe_allow_html=True)
    with rg4:
        st.markdown(f"""<div class='issue-card' style='border-top-color:{ACCENT}'>
            <div class='issue-title'>逆流(アニメーション工程から)</div>
            <div class='issue-body'>発生率 <span class='issue-num'>{r_rate:.0%}</span><br>
            パブリッシュ後、実際にアニメーターが動かして初めて発覚する不具合。
            通常のガントチャートでは見えず、プロセスマイニングで初めて可視化できる部分。</div></div>""",
            unsafe_allow_html=True)

# ── CG業界特有の経営課題 ────────────────────────────────
st.markdown("<div class='sec'>CG業界特有の経営課題（データから検出）</div>", unsafe_allow_html=True)

by_artist = fdf.groupby("artist").agg(n=("shot_id","nunique"),
                                       late_rate=("is_late","mean")).reset_index()
top_artist = by_artist.sort_values("n",ascending=False).iloc[0]

crev = fdf[fdf["client_review"]]
c_reject_rate = crev["client_reject"].mean() if len(crev) else 0.0
c_extra_days  = crev.loc[crev["client_reject"],"client_days"].mean() if crev["client_reject"].any() else 0.0

hold_df = fdf[fdf["stage"].map(lambda s: TASK_CONFIG[s]["upstream"] is not None)]
hold_rate2 = hold_df["hold"].mean()
hold_days_avg = hold_df.loc[hold_df["hold"],"hold_days"].mean() if hold_df["hold"].any() else 0.0

anim = fdf[fdf["stage"]=="アニメーション"]
anim_total_extra = anim["delay"].mean()

i1,i2,i3,i4 = st.columns(4)
with i1:
    st.markdown(f"""<div class='issue-card'>
        <div class='issue-title'>属人化リスク</div>
        <div class='issue-body'><span class='issue-num'>{top_artist['artist']}</span>に
        担当ショットが集中。特定アーティスト依存度が高い工程は、その人物の離脱・多忙が
        全体スケジュールに直結する。</div></div>""", unsafe_allow_html=True)
with i2:
    st.markdown(f"""<div class='issue-card'>
        <div class='issue-title'>クライアントレビュー往復コスト</div>
        <div class='issue-body'>クライアント差し戻し率
        <span class='issue-num'>{c_reject_rate:.0%}</span>。
        1回の差し戻しで平均{c_extra_days:.1f}日の追加が発生し、外部要因による
        スケジュール遅延の主因になりやすい。</div></div>""", unsafe_allow_html=True)
with i3:
    st.markdown(f"""<div class='issue-card'>
        <div class='issue-title'>上流変更の下流波及</div>
        <div class='issue-body'>モデリング／レイアウトの手戻りが下流工程の
        <span class='issue-num'>{hold_rate2:.0%}</span>で保留（平均{hold_days_avg:.1f}日）を誘発。
        並行作業の前提が崩れ、見えない停滞を生む。</div></div>""", unsafe_allow_html=True)
with i4:
    st.markdown(f"""<div class='issue-card'>
        <div class='issue-title'>アニメーション工程の複合リスク</div>
        <div class='issue-body'>内部差し戻し・保留・クライアント差し戻しが重なりやすく、
        平均<span class='issue-num'>{anim_total_extra:.1f}日</span>の遅延が集中。
        単一工程だが実質的に最大のボトルネック。</div></div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Heatmap + Histogram ───────────────────────────────
r3l, r3r = st.columns([3,2])

with r3l:
    st.markdown("<div class='sec'>アーティスト × 工程　平均リビジョン回数</div>",
                unsafe_allow_html=True)
    hp = fdf.groupby(["artist","stage"])["revision"].mean().reset_index()
    pv = hp.pivot(index="artist",columns="stage",values="revision").fillna(0)
    pv = pv[[s for s in STAGES if s in pv.columns]]
    fig_h = go.Figure(go.Heatmap(
        z=pv.values, x=pv.columns.tolist(), y=pv.index.tolist(),
        colorscale=[[0,PALE],[0.4,STEEL],[1,WARN]],
        hovertemplate="<b>%{y} × %{x}</b><br>平均: %{z:.2f}回<extra></extra>",
        text=np.round(pv.values,1), texttemplate="%{text}",
        textfont=dict(size=10)
    ))
    fig_h.update_layout(height=290,margin=dict(t=8,b=8,l=10,r=10),
                        paper_bgcolor="white",
                        font=dict(family="Yu Gothic UI",size=10))
    st.plotly_chart(fig_h, use_container_width=True)

with r3r:
    st.markdown("<div class='sec'>ショット別　遅延日数の分布</div>",
                unsafe_allow_html=True)
    sd2 = fdf.groupby("shot_id")["delay"].sum().reset_index()
    avg_d = sd2["delay"].mean()
    fig_hist = px.histogram(sd2,x="delay",nbins=25,
        color_discrete_sequence=[STEEL],
        labels={"delay":"合計遅延日数","count":"ショット数"})
    fig_hist.add_vline(x=avg_d,line_dash="dash",line_color=WARN,
        annotation_text=f"平均 {avg_d:.1f}日",
        annotation_font_color=WARN,annotation_position="top right")
    fig_hist.update_layout(height=290,margin=dict(t=8,b=8,l=10,r=10),
        paper_bgcolor="white",plot_bgcolor="white",bargap=0.08,
        font=dict(family="Yu Gothic UI",size=11))
    fig_hist.update_yaxes(gridcolor="#EEF2F6")
    st.plotly_chart(fig_hist, use_container_width=True)

# ── AI ANALYSIS ───────────────────────────────────────
st.markdown("<div class='sec'>🤖 AI プロセス診断（Claude API）</div>",
            unsafe_allow_html=True)

if st.button("▶ AI診断を実行", type="primary"):
    if not api_key:
        st.warning("サイドバーにClaude API Keyを入力してください。")
    else:
        ss2 = fdf.groupby("stage").agg(
            avg_actual =("actual","mean"),
            avg_planned=("planned","mean"),
            rev_rate   =("revision",lambda x:(x>0).mean()),
            avg_rev    =("revision","mean"),
        ).round(2).reset_index()
        ss2 = ss2[ss2["stage"].isin(STAGES)]

        top5 = fdf.groupby("shot_id").agg(
            total_delay=("delay","sum"),
            project    =("project","first"),
            complexity =("complexity","first"),
        ).nlargest(5,"total_delay").reset_index()

        prompt = f"""あなたはCG制作プロダクションのプロセス改善コンサルタントです。
以下のデータを分析し、日本語で経営者向け診断レポートを作成してください。

【分析対象】{sel}
【ショット総数】{shots}件　【平均遅延】{avg_delay:.1f}日/ショット
【総リビジョン】{total_rev}回　【期限内完了率】{on_time:.0f}%

【工程】{" → ".join(STAGES)}

【工程別パフォーマンス】
{ss2.to_string(index=False)}

【業界特有の経営課題（検出値）】
・属人化：{top_artist['artist']} にショットが集中
・クライアントレビュー差し戻し率：{c_reject_rate:.0%}（平均{c_extra_days:.1f}日/回の追加）
・上流工程の手戻りによる下流保留率：{hold_rate2:.0%}（平均{hold_days_avg:.1f}日/件）

【リギング工程：差し戻し要因の内訳】
・ウェイト不良（スキニング起因）：{(fdf[fdf['stage']=='リギング']['rework_cause']=='ウェイト不良').mean():.0%}
・補正シェイプ不足（デフォーメーション破綻）：{(fdf[fdf['stage']=='リギング']['rework_cause']=='補正シェイプ不足').mean():.0%}
・検証NG（命名/性能）：{(fdf[fdf['stage']=='リギング']['rework_cause']=='検証NG').mean():.0%}
・アニメーション工程からの逆流（パブリッシュ後の事後差し戻し）：{fdf[fdf['stage']=='リギング']['downstream_recall'].mean():.0%}

【遅延上位5ショット】
{top5.to_string(index=False)}

以下の構成で簡潔・具体的に答えてください：

## 🔍 最重要ボトルネック
（1〜2工程を具体的に。数値を使って）

## 📊 遅延の根本原因
（データから読み取れる構造的な問題を2〜3点。属人化・クライアントレビュー往復・上流波及のいずれかに触れること）

## ✅ 即実行できる改善アクション
（3つ。各1〜2文で）

## ⚠️ 納期リスク評価
（高/中/低とその根拠を1〜2文で）"""

        with st.spinner("Claudeが分析中...（10〜20秒）"):
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type":"application/json",
                             "x-api-key":api_key,
                             "anthropic-version":"2023-06-01"},
                    json={"model":"claude-sonnet-4-6","max_tokens":1200,
                          "messages":[{"role":"user","content":prompt}]},
                    timeout=40
                )
                if resp.status_code==200:
                    st.markdown(
                        f"<div class='ai-box'>{resp.json()['content'][0]['text']}</div>",
                        unsafe_allow_html=True)
                else:
                    st.error(f"APIエラー {resp.status_code}: {resp.text}")
            except Exception as e:
                st.error(f"エラー: {e}")
else:
    st.markdown(f"""<div class='hint'>▶ ボタンを押すと Claudeがプロセスデータを分析し、
    <b>ボトルネック特定・根本原因（属人化／クライアントレビュー往復／上流波及を含む）・改善アクション・納期リスク評価</b>を自動生成します。
    サイドバーにClaude API Keyが必要です。</div>""", unsafe_allow_html=True)

st.divider()
st.caption("NeXT Diagnostics Demo v3.0　｜　工程レベル俯瞰＋業務手順レベルのドリルダウン対応　｜　データはデモ用サンプルです")
