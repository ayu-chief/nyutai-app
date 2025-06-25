import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from calendar import monthrange
from st_aggrid import AgGrid, GridOptionsBuilder
import requests
import jpholiday
import re

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
                st.rerun()   # ←ここを修正しました！
            else:
                st.error("パスワードが違います")
    st.stop()  # 正しく認証されるまで以降の処理は実行されません

# ===== 設定 =====
GRADE_NAMES = {
    11: "小学1年生", 12: "小学2年生", 13: "小学3年生", 14: "小学4年生",
    15: "小学5年生", 16: "小学6年生",
    21: "中学1年生", 22: "中学2年生", 23: "中学3年生",
    31: "高校1年生", 32: "高校2年生", 33: "高校3年生",
    60: "社会人", 99: "その他",
    71: "年少組", 72: "年中組", 73: "年長組"
}
API_TOKEN = "41eL_54-bynysLzAsmad"
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

# ===== ページ切替 =====
page = st.sidebar.selectbox("ページを選択", ["本日の出席一覧", "入退室一覧"])

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

        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True
        )
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
    for d in range(1, days_in_month+1):
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
    att_dict = {}
    for rec in attendance:
        uid = rec["user_id"]
        dt_in = rec.get("entrance_time")
        dt_out = rec.get("exit_time")
        if dt_in:
            d = datetime.fromisoformat(dt_in).day
            att_dict[(uid, d)] = (dt_in, dt_out)

    table = []
    for stu in students:
        row = {"学年": GRADE_NAMES.get(stu.get("grade_id"), "不明"), "生徒名": stu["name"]}
        for d in range(1, days_in_month+1):
            v = att_dict.get((stu["id"], d))
            if v:
                row[days[d-1]] = f"{to_hm(v[0])}-{to_hm(v[1])}"
            else:
                row[days[d-1]] = "-"
        table.append(row)
    df_all = pd.DataFrame(table)

    csv = df_all.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="この一覧をCSVでダウンロード",
        data=csv,
        file_name=f"{year}年{month}月_入退室一覧.csv",
        mime='text/csv'
    )

    def header_color(s):
        color_row = []
        for i, col in enumerate(s.index):
            if i < 2:
                color_row.append("background-color: #e8e8e8")
            else:
                color_row.append(f"background-color: {colors[i-2]}")
        return color_row

    styled = df_all.style.apply(header_color, axis=1)

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True
    )
