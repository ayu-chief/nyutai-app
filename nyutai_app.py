import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from calendar import monthrange
from st_aggrid import AgGrid, GridOptionsBuilder
import requests
import jpholiday
import re

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# ↓ここをSecretsから認証する形に修正！
service_account_info = st.secrets["gcp_service_account"]  # secrets名と合わせてください
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
gc = gspread.authorize(creds)

SPREADSHEET_KEY = "14xpU7k_Kh_s-ciOWeeaHcoi8NYDfYMpn1Lri3lSKOLc"
sh = gc.open_by_key(SPREADSHEET_KEY)
worksheet = sh.sheet1  # 一番左のシート

# ====== 日付が変わったら自動リロード ======
from datetime import date
import streamlit as st

today_str = date.today().isoformat()

# 先にセッション状態を初期化
if "last_run_date" not in st.session_state:
    st.session_state["last_run_date"] = today_str

# 日付が変わった場合はセッションをリセット＋再実行
if st.session_state["last_run_date"] != today_str:
    st.session_state.clear()   # これで全セッション変数をリセット
    st.session_state["last_run_date"] = today_str
    st.rerun()

# ====== パスワード認証（当日中有効） ======
PASSWORD = "kawasaki"   # ここを書き換えて運用してください

today_str = date.today().isoformat()
auth_key = f"authenticated_{today_str}"

if not st.session_state.get(auth_key):
    with st.form("login_form"):
        st.markdown("### パスワードを入力してください")
        password_input = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")
        if submitted:
            if password_input == PASSWORD:
                st.session_state[auth_key] = True
                st.success("認証成功！")
                st.rerun()
            else:
                st.error("パスワードが違います")
    st.stop()  # 正しく認証されるまで以降の処理は実行されません

# ======= サイドバー誘導の案内文をメイン画面上部に追加 ==========
st.markdown(
    '<span style="color:gray;font-size:90%;">'
    '画面左のサイドバーから「月ごとの入退室一覧」が表示できます。<br>'
    '※サイドバーが見えない場合は左上の >> ボタンを押してください。'
    '</span>',
    unsafe_allow_html=True
)

# ===== 設定 =====
GRADE_NAMES = {
    11: "小学1年生", 12: "小学2年生", 13: "小学3年生", 14: "小学4年生",
    15: "小学5年生", 16: "小学6年生",
    21: "中学1年生", 22: "中学2年生", 23: "中学3年生",
    31: "高校1年生", 32: "高校2年生", 33: "高校3年生",
    60: "社会人", 99: "その他",
    71: "年少組", 72: "年中組", 73: "年長組"
}
API_TOKEN = "41eL_54-bynysLzAsmad"   # ここを各校舎のトークンに変更するだけで名簿変更可能
API_BASE = "https://site1.nyutai.com/api/chief/v1"
headers = {"Api-Token": API_TOKEN}

# ===== ユーティリティ =====
def get_students():
    url = f"{API_BASE}/students"
    res = requests.get(url, headers=headers)
    return res.json()["data"]

def get_attendance(date_from, date_to=None):
    url = f"{API_BASE}/entrance_and_exits"
    params = {"date_from": date_from}
    if date_to:
        params["date_to"] = date_to
    res = requests.get(url, headers=headers, params=params)
    return res.json()["data"]

def to_hm(dt_str):
    if not dt_str or dt_str == "-":
        return "-"
    try:
        return datetime.fromisoformat(dt_str).strftime("%H:%M")
    except Exception:
        return "-"

def get_month_list(n=12):
    today = date.today().replace(day=1)
    months = []
    for i in range(n):
        m = today - timedelta(days=1)
        months.append(m.strftime("%Y年%m月"))
        today = m.replace(day=1)
    months = [date.today().strftime("%Y年%m月")] + months  # 今月を先頭
    return months

# ====== サイドバーに見出しを追加 ==========
with st.sidebar:
    st.markdown("### 📅 メニュー")

# ===== ページ切替 =====
page = st.sidebar.selectbox(
    "ページを選択",
    ["本日の出席一覧", "入退室一覧", "月別報告書一覧"]
)

# ===== 1. 本日の出席一覧 =====
if page == "本日の出席一覧":
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"]
    today_obj = date.today()
    weekday = weekday_kanji[today_obj.weekday()]
    today_str = today_obj.strftime(f"%Y年%m月%d日（{weekday}）")
    st.markdown(f"### {today_str}")

    st.title("本日の出席一覧")
    today = date.today().isoformat()

    students = get_students()
    students = sorted(students, key=lambda x: x.get("grade_id") or 999)
    attendance = get_attendance(today, today)
    att_dict = {a["user_id"]: a for a in attendance}

    table = []
    present_flags = []
    for stu in students:
        att = att_dict.get(stu["id"], {})
        grade_id = stu.get("grade_id")
        grade_name = GRADE_NAMES.get(grade_id, "不明")
        is_present = bool(att.get("entrance_time") and not att.get("exit_time"))
        present_flags.append(is_present)
        row = {
            "学年": grade_name,
            "生徒名": stu["name"],
            "ステータス": "出席" if att.get("entrance_time") else "未出席",
            "入室": to_hm(att.get("entrance_time", "-")),
            "退室": to_hm(att.get("exit_time", "-")),
        }
        table.append(row)

    now_present_count = sum(1 for flag in present_flags if flag)
    today_attendance_count = sum(1 for stu in students if att_dict.get(stu["id"], {}).get("entrance_time"))

    st.markdown(f"**いま出席中の人数：{now_present_count} 人**")
    st.markdown(f"**本日の合計出席者数：{today_attendance_count} 人**")

    df = pd.DataFrame(table)

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_selection(selection_mode="single", use_checkbox=True)
    grid_options = gb.build()
    response = AgGrid(
        df,
        gridOptions=grid_options,
        fit_columns_on_grid_load=True,
        height=400,
    )
    selected_rows = response["selected_rows"]

    if selected_rows is not None and len(selected_rows) > 0:
        selected_name = selected_rows.iloc[0]["生徒名"]
        selected_student = next(stu for stu in students if stu["name"] == selected_name)
        selected_id = selected_student["id"]

        today = date.today()
        year, month = today.year, today.month
        days_in_month = monthrange(year, month)[1]

        date_from = f"{year}-{month:02d}-01"
        date_to = f"{year}-{month:02d}-{days_in_month:02d}"
        attendance_month = get_attendance(date_from, date_to)
        records = [rec for rec in attendance_month if rec["user_id"] == selected_id]

        day2times = {}
        present_days = set()
        for rec in records:
            dt_in = rec.get("entrance_time")
            dt_out = rec.get("exit_time")
            day = None
            if dt_in:
                day = datetime.fromisoformat(dt_in).day
            if day:
                label = f"{day}\n{to_hm(dt_in) if dt_in else '-'}-{to_hm(dt_out) if dt_out else '-'}"
                day2times[day] = label
                present_days.add(day)

        # manual_attendance.csvをマージ
        import os
        manual_csv = "manual_attendance.csv"
        if os.path.exists(manual_csv):
            df_manual = pd.read_csv(manual_csv)
            manual_records = df_manual[
                (df_manual["生徒名"] == selected_name) &
                (df_manual["日付"].str.startswith(f"{year}-{month:02d}-"))
            ]
            for _, row in manual_records.iterrows():
                d = int(row["日付"].split("-")[2])
                day2times[d] = f"{d}\n{row['入室']}-{row['退室']}"
                present_days.add(d)

        first_day_weekday = date(year, month, 1).weekday()
        start_padding = (first_day_weekday + 1) % 7
        calendar_cells = []
        for d in range(1, days_in_month+1):
            if d in day2times:
                s = day2times[d]
            else:
                s = f"{d}\n-"
            calendar_cells.append(s)
        calendar_days = [""] * start_padding + calendar_cells
        while len(calendar_days) % 7 != 0:
            calendar_days.append("")
        calendar_matrix = np.array(calendar_days).reshape(-1, 7)

        cal_df = pd.DataFrame(calendar_matrix, columns=["日","月","火","水","木","金","土"])

        def is_empty_row(row):
            for cell in row:
                s = str(cell).strip()
                if s in ["", "-"]:
                    continue
                if re.match(r"^\d+\n-$", s):
                    continue
                return False
            return True

        cal_df = cal_df[~cal_df.apply(is_empty_row, axis=1)]

        st.subheader("今月の入退室状況")

        def color_cell(val):
            if not val or "\n" not in str(val):
                return "background-color: #eeeeee; font-size: 1.2em; line-height: 1.6;"
            day_str = str(val).split("\n")[0]
            try:
                day = int(day_str)
                thisdate = date(year, month, day)
            except:
                return "background-color: #eeeeee; font-size: 1.2em; line-height: 1.6;"
            if jpholiday.is_holiday(thisdate):
                base = "background-color: #ffc1c1;"  # 祝日ピンク
            elif thisdate.weekday() == 6:
                base = "background-color: #ffb3b3;"  # 日曜
            elif thisdate.weekday() == 5:
                base = "background-color: #bbd6ff;"  # 土曜
            elif day in present_days:
                base = "background-color: #b7eeb7;"  # 出席緑
            else:
                base = "background-color: #eeeeee;"  # その他グレー
            return f"{base} font-size: 1.2em; line-height: 1.5;"

        styled = cal_df.style.applymap(color_cell)

        # ▼ カレンダー表示
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True
        )

        # ▼ カレンダー下に「打刻手入力フォーム」を追加
        st.markdown("---")
        st.markdown("#### この生徒の打刻漏れ修正")
        with st.form(f"manual_attendance_edit_{selected_name}_{year}_{month}"):
            edit_day = st.selectbox(
                "修正する日付",
                [f"{year}-{month:02d}-{d:02d}" for d in range(1, days_in_month+1)],
                key=f"edit_day_{selected_name}_{year}_{month}"
            )
            manual_in = st.time_input("入室時刻", value=None, key=f"manual_in_{selected_name}_{year}_{month}")
            manual_out = st.time_input("退室時刻", value=None, key=f"manual_out_{selected_name}_{year}_{month}")
            submitted = st.form_submit_button("この内容で修正する")
            if submitted:
                manual_csv = "manual_attendance.csv"
                new_row = {
                    "生徒名": selected_name,
                    "日付": edit_day,
                    "入室": manual_in.strftime("%H:%M") if manual_in else "-",
                    "退室": manual_out.strftime("%H:%M") if manual_out else "-"
                }
                import pandas as pd
                if os.path.exists(manual_csv):
                    df = pd.read_csv(manual_csv)
                    mask = (df["生徒名"] == selected_name) & (df["日付"] == edit_day)
                    if mask.any():
                        df.loc[mask, ["入室", "退室"]] = [new_row["入室"], new_row["退室"]]
                    else:
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    df.to_csv(manual_csv, index=False, encoding="utf-8-sig")
                else:
                    df = pd.DataFrame([new_row])
                    df.to_csv(manual_csv, index=False, encoding="utf-8-sig")
                st.success(f"{edit_day} の記録を修正しました！")
                st.rerun()  # ★ これで即時カレンダー反映
         # ▼ この日付の手入力を削除（API記録に戻す）
        st.markdown("##### 手入力打刻をリセット（API記録に戻す）")
        if st.button("カレンダーで日付を選択して入退くんの記録に戻す", key=f"reset_{selected_name}_{edit_day}"):
            manual_csv = "manual_attendance.csv"
            import os
            import pandas as pd
            if os.path.exists(manual_csv):
                df = pd.read_csv(manual_csv)
                mask = (df["生徒名"] == selected_name) & (df["日付"] == edit_day)
                if mask.any():
                    df = df[~mask]
                    df.to_csv(manual_csv, index=False, encoding="utf-8-sig")
                    st.success(f"{edit_day} の手入力を削除し、API記録に戻しました！")
                else:
                    st.info("この日の手入力修正はありません。")
            else:
                st.info("手入力記録ファイルが存在しません。")
            st.rerun()

    else:
        st.info("出席一覧から生徒名を選択してください。")

# ===== 2. 入退室一覧（月選択対応） =====
elif page == "入退室一覧":
    st.title("入退室一覧")

    # ▼ 月選択肢
    month_options = get_month_list(12)
    selected_month = st.sidebar.selectbox("表示する月", month_options)
    m = re.match(r"(\d+)年(\d+)月", selected_month)
    year, month = int(m.group(1)), int(m.group(2))
    days_in_month = monthrange(year, month)[1]

    # 日付＋曜日ラベル・色
    days = []
    colors = []
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"]
    for d in range(1, days_in_month + 1):
        dt = date(year, month, d)
        wd = dt.weekday()
        label = f"{d}（{weekday_kanji[wd]}）"
        days.append(label)
        if jpholiday.is_holiday(dt):
            colors.append("#ffc1c1")
        elif wd == 6:
            colors.append("#ffb3b3")
        elif wd == 5:
            colors.append("#bbd6ff")
        else:
            colors.append("#ffffff")

    students = get_students()
    students = sorted(students, key=lambda x: x.get("grade_id") or 999)
    date_from = f"{year}-{month:02d}-01"
    date_to = f"{year}-{month:02d}-{days_in_month:02d}"
    attendance = get_attendance(date_from, date_to)

    # (user_id, 日) の dict
    att_dict = {}
    for rec in attendance:
        uid = rec["user_id"]
        dt_in = rec.get("entrance_time")
        dt_out = rec.get("exit_time")
        if dt_in:
            d = datetime.fromisoformat(dt_in).day
            att_dict[(uid, d)] = (dt_in, dt_out)

    # ▼ 生徒ごと×日で表を作る
    table = []
    for stu in students:
        row = {"学年": GRADE_NAMES.get(stu.get("grade_id"), "不明"), "生徒名": stu["name"]}
        for d in range(1, days_in_month + 1):
            v = att_dict.get((stu["id"], d))
            if v:
                # 2行表示（AgGrid用に<br>に置換）
                row[days[d-1]] = f"{to_hm(v[0])}\n{to_hm(v[1])}"
            else:
                row[days[d-1]] = "-"
        table.append(row)
    df_all = pd.DataFrame(table)

    # CSVダウンロード（改行は \n に戻してエクスポート）
    df_csv = df_all.copy()
    for col in df_csv.columns:
        if col not in ("学年", "生徒名"):
            df_csv[col] = df_csv[col].astype(str).str.replace("<br>", "\n")
    csv = df_csv.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="この一覧をCSVでダウンロード",
        data=csv,
        file_name=f"{year}年{month}月_入退室一覧.csv",
        mime='text/csv'
    )

    # --- AgGridでセル2行表示 ---
    from st_aggrid import AgGrid, GridOptionsBuilder

    gb = GridOptionsBuilder.from_dataframe(df_all)
    gb.configure_column("学年", width=80)
    gb.configure_column("生徒名", width=120)
    for col in df_all.columns:
        if col not in ("学年", "生徒名"):
            gb.configure_column(
                col,
                width=80,
                cellRenderer='''(params) => `<div style="white-space:pre-line;line-height:1.4em">${params.value || ""}</div>`''',
                autoHeight=True  # ←これも追加すると、2行目があっても行の高さが自動調整される
            )
    grid_options = gb.build()

    AgGrid(
        df_all,
        gridOptions=grid_options,
        allow_unsafe_jscode=True,  # ←これを絶対Trueにする
        fit_columns_on_grid_load=False,  # ←ここもFalseにするのがコツ！
        height=500,
    )

elif page == "月別報告書一覧":
    st.title("月別・生徒別 報告書一覧")
    import os
    import pandas as pd

    save_file = "reports.csv"
    if not os.path.exists(save_file):
        st.warning("まだ報告が保存されていません。")
        st.stop()

    df = pd.read_csv(save_file)
    df["年"] = pd.to_numeric(df["年"], errors="coerce").astype("Int64")
    df["月"] = pd.to_numeric(df["月"], errors="coerce").astype("Int64")

    # ▼ サイドバーで年・月を選択
    years = sorted(df["年"].dropna().unique())
    months = sorted(df["月"].dropna().unique())
    sel_year = st.sidebar.selectbox("年", years, index=len(years)-1)
    sel_month = st.sidebar.selectbox("月", months, index=len(months)-1)

    # 生徒情報をAPIなどから取得（学年も含める）
    students = get_students()  # 例: [{"id":1,"name":"田中太郎","grade_id":12}, ...]
    students = sorted(students, key=lambda x: x.get("grade_id") or 999)
    grade_map = GRADE_NAMES

    # 今月分データ
    filtered = df[(df["年"] == sel_year) & (df["月"] == sel_month)]

    # 生徒ごとに内容をまとめる
    table = []
    for stu in students:
        name = stu["name"]
        grade_id = stu.get("grade_id")
        grade_name = grade_map.get(grade_id, "不明")
        row_data = filtered[filtered["生徒名"] == name]
        if len(row_data) > 0:
            row = {
                "学年": grade_name,
                "生徒名": name,
                "内容": row_data.iloc[0]["内容"],
                "記入日時": row_data.iloc[0]["記入日時"]
            }
        else:
            row = {
                "学年": grade_name,
                "生徒名": name,
                "内容": "未入力",
                "記入日時": "-"
            }
        table.append(row)

    df_show = pd.DataFrame(table)

    # ▼ 「未入力」を赤字・太字で
    def color_unentered(val):
        if val == "未入力":
            return "color: red; font-weight: bold;"
        return ""
    styled = df_show.style.applymap(color_unentered, subset=["内容"])

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ▼ CSVダウンロード
    csv = df_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label=f"{sel_year}年{sel_month}月_全員分_報告書一覧.csv をダウンロード",
        data=csv,
        file_name=f"{sel_year}年{sel_month}月_全員分_報告書一覧.csv",
        mime='text/csv'
    )
