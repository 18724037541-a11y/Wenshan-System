import streamlit as st
import sqlite3, json, os, pandas as pd, subprocess
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# ==========================================
# 🍎 极致 UI 配置与视觉唤醒
# ==========================================
st.set_page_config(page_title="文杉 WENSHAN | 智能学情分析", layout="wide", page_icon="🍃")
st.markdown("""<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    [data-testid="stHeader"], footer {display: none;}
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(120deg, #fdfbfb 0%, #ebedee 100%);
        background-image: radial-gradient(at 0% 0%, rgba(220, 233, 255, 0.6) 0px, transparent 50%),
                          radial-gradient(at 100% 0%, rgba(240, 220, 255, 0.5) 0px, transparent 50%),
                          radial-gradient(at 100% 100%, rgba(220, 255, 240, 0.5) 0px, transparent 50%);
        background-attachment: fixed; font-family: 'Inter', sans-serif !important; color: #1d1d1f;
    }
    .glass-panel, div[data-testid="stForm"] {
        background: rgba(255, 255, 255, 0.6) !important; backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.8) !important; border-radius: 24px !important; padding: 1.5rem; 
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.04) !important; transition: transform 0.4s ease, box-shadow 0.4s ease;
    }
    .list-card {
        background: white; border-radius: 16px; padding: 20px; margin-bottom: 15px; border: 1px solid rgba(0,0,0,0.05); box-shadow: 0 2px 10px rgba(0,0,0,0.02); display: flex; flex-direction: column;
    }
    .stButton > button { border-radius: 980px; font-weight: 600; width: 100%; transition: all 0.3s ease; border: 1px solid rgba(0,0,0,0.1); }
    button[kind="primary"] {
        background: linear-gradient(135deg, #0071e3 0%, #4facfe 100%) !important; color: white !important; border: none !important; box-shadow: 0 4px 15px rgba(0, 113, 227, 0.3) !important;
    }
    button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0, 113, 227, 0.5) !important; }
    h1 { font-weight: 700; font-size: 44px !important; letter-spacing: -0.03em; background: linear-gradient(90deg, #1d1d1f, #434344); -webkit-background-clip: text; -webkit-text-fill-color: transparent;}
    [data-testid="stMetricValue"] { font-weight: 700; font-size: 36px; background: linear-gradient(135deg, #0071e3, #4facfe); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
</style>""", unsafe_allow_html=True)

# ！！！请填入你的 API KEY ！！！
genai.configure(api_key=st.secrets["GEMINI_API_KEY"]) 

# 🚀 终极智能寻路逻辑：自动匹配账号模型，且精准避开报错模型
try:
    # 1. 获取你账号下所有支持生成内容的模型
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    
    # 2. 🛑 核心过滤：坚决排除掉那个会报 400 错误的 robotics 模型
    safe_models = [m for m in available_models if 'robotics' not in m]
    
    # 3. 按优先级寻找能看图的最强模型 (1.5-flash -> 1.5-pro -> vision)
    best_model_name = next((m for keyword in ['1.5-flash', '1.5-pro', 'vision', 'pro'] for m in safe_models if keyword in m), safe_models[-1] if safe_models else 'gemini-1.5-flash-latest').replace('models/', '')
    
    model = genai.GenerativeModel(best_model_name)
    
except Exception as e:
    model = None
    st.error(f"🚨 AI 引擎初始化失败！具体原因：{str(e)}")

# ==========================================
# ⚙️ 数据库与云端永生备份引擎 (核心科技)
# ==========================================
SUBJECTS = ["物理", "化学", "生物", "语文", "数学", "英语"]

def init_db():
    for folder in ["scans_multi", "exports"]:
        if not os.path.exists(folder): os.makedirs(folder)
    conn = sqlite3.connect("wenshan_cloud.db")
    conn.execute('''CREATE TABLE IF NOT EXISTS templates (id INTEGER PRIMARY KEY AUTOINCREMENT, exam_name TEXT UNIQUE, subject TEXT, schema_json TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, student_name TEXT, exam_name TEXT, subject TEXT, obj_score REAL, subj_score REAL, total_score REAL, details TEXT, exam_folder TEXT, scan_date TEXT)''')
    conn.commit(); conn.close()

def auto_backup():
    """将数据永生备份到 GitHub 的核心函数"""
    try:
        # 如果我们在 Streamlit 云端，并且配置了 Secrets，就执行备份
        if "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            repo = st.secrets["GITHUB_REPO"]
            remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
            
            # 使用 git 命令提交数据
            subprocess.run(['git', 'config', '--global', 'user.email', 'bot@wenshan.com'])
            subprocess.run(['git', 'config', '--global', 'user.name', 'Wenshan Cloud Bot'])
            subprocess.run(['git', 'remote', 'set-url', 'origin', remote_url])
            subprocess.run(['git', 'add', 'wenshan_cloud.db', 'scans_multi/'])
            subprocess.run(['git', 'commit', '-m', f'Auto backup at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
            subprocess.run(['git', 'push', 'origin', 'HEAD'])
    except Exception as e:
        print(f"备份失败: {e}")

init_db()

# ==========================================
# 🧠 AI 引擎与图像引擎
# ==========================================
def ai_parse_exam_paper(file_bytes, mime_type):
    prompt = """提取试卷结构，分类为 single_choice, multiple_choice, subjective。格式要求：{"single_choice": ["T1"], "multiple_choice": [], "subjective": ["T11"]} 只返回 JSON，不要 Markdown。"""
    try: return json.loads(model.generate_content([prompt, {"mime_type": mime_type, "data": file_bytes}]).text.replace('```json', '').replace('```', '').strip())
    except Exception as e: return {"error": str(e)}

def generate_ai_comment(name, subject, total_score, obj_score, subj_score):
    prompt = f"你是一位温柔的{subject}老师。你的学生【{name}】本次测试考了 {total_score} 分（客观题 {obj_score} 分，主观题 {subj_score} 分）。请用 50 字左右写一段温和的鼓励评语。像真人在说话。"
    try: return model.generate_content(prompt).text
    except: return "AI 导师暂时在休息，但你的努力已被文杉系统见证，继续加油！"

def draw_score_stamp(image_path, details_dict, total_score):
    try:
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        try: font = ImageFont.truetype("Arial.ttf", 40)
        except: font = ImageFont.load_default()
        stamp_x, stamp_y = 60, 60
        box_width = 380; box_height = 120 + len(details_dict) * 45
        draw.rectangle([stamp_x, stamp_y, stamp_x + box_width, stamp_y + box_height], fill=(255, 250, 250), outline="red", width=4)
        y_offset = stamp_y + 25
        draw.text((stamp_x + 30, y_offset), f"WENSHAN 阅卷统分", fill="red", font=font)
        y_offset += 50
        draw.text((stamp_x + 30, y_offset), f"总得分: {total_score} 分", fill="red", font=font)
        y_offset += 50
        draw.line([stamp_x, y_offset, stamp_x + box_width, y_offset], fill="red", width=2)
        y_offset += 20
        for q, s in details_dict.items():
            draw.text((stamp_x + 50, y_offset), f"{q} :   {s} 分", fill="red", font=font)
            y_offset += 45
        img.save(image_path)
    except: pass

# ==========================================
# 🏠 系统导航与解锁
# ==========================================
col_logo, col_title = st.columns([1, 18], vertical_alignment="center")
with col_logo:
    if os.path.exists("logo.png"): st.image("logo.png", width=45)
with col_title:
    st.markdown("<h3 style='margin: 0; padding-top: 5px; font-weight: 700; letter-spacing: -0.01em;'>文杉 WENSHAN <span style='font-size: 15px; font-weight: 400; color: #86868b; margin-left: 10px; letter-spacing: 0.05em;'>智能学习系统</span></h3>", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

mode = st.radio("导航", ["📑 试卷基准与模板录入", "👨‍🏫 协同阅卷工作台", "🎓 学情档案检索", "📊 班级全景分析"], horizontal=True, label_visibility="collapsed")
st.markdown("<hr style='margin-top: 5px; margin-bottom: 30px; border: none; height: 1px; background: linear-gradient(90deg, transparent, rgba(0,0,0,0.1), transparent);'>", unsafe_allow_html=True)

def check_password():
    if st.session_state.get('auth', False): return True
    st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
    st.markdown("### 🔒 教务系统已锁定")
    pwd = st.text_input("请输入管理密钥", type="password", placeholder="Admin Key (wenshan123)")
    if st.button("🔓 解锁核心引擎", type="primary"):
        if pwd == "wenshan123": st.session_state['auth'] = True; st.rerun()
        else: st.error("密钥错误，请重试。")
    st.markdown("</div>", unsafe_allow_html=True)
    return False

# ------------------------------------------
# 模式一：📑 试卷基准与模板录入
# ------------------------------------------
if mode == "📑 试卷基准与模板录入":
    if check_password():
        st.markdown("<h1>Template Builder.</h1>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        exam_name = c1.text_input("测评名称 (必填)", placeholder="例如：2026.4 物理检测")
        subject = c2.selectbox("学科", SUBJECTS)
        
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        master_file = st.file_uploader("1. 上传空白母卷 (PDF 或 图片)", type=['pdf', 'jpg', 'jpeg', 'png'])
        if 'schema_df' not in st.session_state: st.session_state['schema_df'] = pd.DataFrame({"题号": ["T1"], "题型": ["单选"], "满分": [4.0]})
        
        if master_file and st.button("🚀 启动 AI 智能解析母卷", type="primary"):
            with st.spinner("大模型正在深度阅读试卷结构..."):
                mime = "application/pdf" if master_file.name.endswith(".pdf") else "image/jpeg"
                parsed = ai_parse_exam_paper(master_file.getvalue(), mime)
                if "error" not in parsed:
                    rows = []
                    for q in parsed.get("single_choice", []): rows.append({"题号": q, "题型": "单选", "满分": 4.0})
                    for q in parsed.get("multiple_choice", []): rows.append({"题号": q, "题型": "多选", "满分": 4.0})
                    for q in parsed.get("subjective", []): rows.append({"题号": q, "题型": "主观", "满分": 10.0})
                    if rows: st.session_state['schema_df'] = pd.DataFrame(rows); st.success(f"✅ AI 识别完成！")
                else: st.error(f"解析失败: {parsed['error']}")
        
        st.markdown("### 📝 2. 配置与核对题目分值")
        edited_df = st.data_editor(st.session_state['schema_df'], num_rows="dynamic", use_container_width=True, hide_index=True)
        
        if st.button("💾 将此结构保存为阅卷模板", type="primary"):
            if not exam_name: st.error("请输入测评名称！")
            else:
                final_schema = {str(r['题号']).strip(): {"type": str(r['题型']).strip(), "score": float(r['满分'])} for _, r in edited_df.iterrows() if str(r['题号']).strip()}
                conn = sqlite3.connect("wenshan_cloud.db")
                try:
                    conn.execute('INSERT INTO templates (exam_name, subject, schema_json) VALUES (?, ?, ?)', (exam_name, subject, json.dumps(final_schema)))
                    conn.commit()
                    
                    # 保存成功后，立即将数据库云端备份
                    with st.spinner("正在将新模板永久备份至云端..."):
                        auto_backup()
                        
                    st.balloons(); st.success(f"✅ 模板【{exam_name}】已入库并云端备份成功！")
                except sqlite3.IntegrityError: st.error("⚠️ 该名称模板已存在！")
                finally: conn.close()
        st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------
# 模式二：👨‍🏫 协同阅卷工作台
# ------------------------------------------
elif mode == "👨‍🏫 协同阅卷工作台":
    if check_password():
        st.markdown("<h1>Collab Desk.</h1>", unsafe_allow_html=True)
        conn = sqlite3.connect("wenshan_cloud.db")
        templates = pd.read_sql_query("SELECT * FROM templates", conn)
        existing_students = pd.read_sql_query("SELECT DISTINCT student_id, student_name FROM results WHERE student_name IS NOT NULL", conn)
        student_dict = dict(zip(existing_students['student_id'], existing_students['student_name']))
        conn.close()
        
        if templates.empty: st.warning("⚠️ 请先建立模板。")
        else:
            sel_exam = st.selectbox("选择要批阅的测评模板", templates['exam_name'].tolist())
            schema = json.loads(templates[templates['exam_name'] == sel_exam].iloc[0]['schema_json'])
            
            col_preview, col_entry = st.columns([6, 5], gap="large")
            with col_preview:
                st.markdown("### 📸 1. 原卷全景视图")
                files = st.file_uploader("拖入【所有答卷图片】", accept_multiple_files=True, type=['jpg', 'jpeg', 'png'])
                if files:
                    with st.container(height=800): 
                        for f in files: st.image(f, use_column_width=True)
            
            with col_entry:
                st.markdown("### 📝 2. 得分极速录入")
                with st.form("grading_form", clear_on_submit=True):
                    c_id, c_name = st.columns(2)
                    sid = c_id.text_input("准考证号 / 学号 *")
                    sname = c_name.text_input("学生姓名 (选填，系统将永久记忆)")
                    
                    st.markdown("---")
                    student_scores = {}
                    col_e1, col_e2 = st.columns(2)
                    for i, (q, info) in enumerate(schema.items()):
                        with col_e1 if i % 2 == 0 else col_e2:
                            student_scores[q] = st.number_input(f"{q} ({info['type']}, 满分{info['score']})", min_value=0.0, max_value=float(info['score']), value=float(info['score']), step=1.0)
                    
                    st.markdown("---")
                    if st.form_submit_button("✅ 盖章、批注并归档", type="primary"):
                        if not sid or not files: st.error("学号和试卷缺一不可！")
                        else:
                            final_name = sname if sname else student_dict.get(sid, "未知姓名")
                            obj_score = sum([s for q, s in student_scores.items() if schema[q]['type'] != "主观"])
                            subj_score = sum([s for q, s in student_scores.items() if schema[q]['type'] == "主观"])
                            total_score = obj_score + subj_score
                            
                            exam_folder = f"scans_multi/{sid}_{sel_exam}_{datetime.now().strftime('%Y%m%d%H%M')}"
                            os.makedirs(exam_folder, exist_ok=True)
                            saved_paths = []
                            for i, f in enumerate(files):
                                path = f"{exam_folder}/Page_{i+1}.jpg"
                                with open(path, "wb") as img_f: img_f.write(f.getvalue())
                                saved_paths.append(path)
                                
                            if saved_paths: draw_score_stamp(saved_paths[0], student_scores, total_score)
                            
                            conn = sqlite3.connect("wenshan_cloud.db")
                            conn.execute('INSERT INTO results VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                         (sid, final_name, sel_exam, templates[templates['exam_name'] == sel_exam].iloc[0]['subject'], obj_score, subj_score, total_score, json.dumps(student_scores), exam_folder, datetime.now().strftime("%Y-%m-%d %H:%M")))
                            conn.commit(); conn.close()
                            
                            # 阅卷完毕，立即将成绩和带红章的试卷备份到云端
                            with st.spinner("正在将学生数据与原卷永久备份至云端..."):
                                auto_backup()
                                
                            st.success(f"✅ 【{final_name}】的档案已归档并云端备份成功！总分 {total_score} 分。")

# ------------------------------------------
# 模式三：🎓 学情档案检索 (完美实现"列表 -> 详情")
# ------------------------------------------
elif mode == "🎓 学情档案检索":
    st.markdown("<h1>Your Archive.</h1>", unsafe_allow_html=True)
    if not st.session_state.get('logged_sid'):
        with st.form("stu_login"):
            st.markdown("### 🎓 学生专属查询入口")
            sid_input = st.text_input("请输入准考证号 / 学号")
            if st.form_submit_button("🔍 检索我的学情报告", type="primary") and sid_input:
                st.session_state['logged_sid'] = sid_input
                st.session_state['archive_view'] = 'list'
                st.rerun()
    else:
        target_sid = st.session_state['logged_sid']
        df = pd.read_sql_query(f"SELECT * FROM results WHERE student_id='{target_sid}' ORDER BY id DESC", sqlite3.connect("wenshan_cloud.db"))
        
        if df.empty:
            st.warning("未能找到相关档案。")
            if st.button("⬅️ 返回重试"):
                st.session_state['logged_sid'] = None; st.rerun()
        else:
            student_name = df.iloc[0]['student_name']
            if st.session_state.get('archive_view', 'list') == 'list':
                c_title, c_btn = st.columns([8, 2], vertical_alignment="bottom")
                c_title.markdown(f"<h2>👋 你好，{student_name}</h2><p style='color:#86868b;'>这里是你所有的学情报告记录</p>", unsafe_allow_html=True)
                if c_btn.button("🚪 退出登录"): st.session_state['logged_sid'] = None; st.rerun()
                
                all_subjects = ["全部"] + list(df['subject'].unique())
                selected_subject = st.radio("筛选学科", all_subjects, horizontal=True, label_visibility="collapsed")
                st.markdown("<br>", unsafe_allow_html=True)
                
                if selected_subject != "全部": df = df[df['subject'] == selected_subject]
                if df.empty: st.info("该学科暂无练习记录。")
                else:
                    for _, row in df.iterrows():
                        st.markdown(f"""
                        <div class='list-card'>
                            <div style='display: flex; justify-content: space-between; align-items: center;'>
                                <div>
                                    <span style='background-color:#e8f0fe; color:#0071e3; padding: 3px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; margin-right:10px;'>{row['subject']}</span>
                                    <span style='color:#86868b; font-size: 14px;'>{row['scan_date']}</span>
                                    <h3 style='margin: 10px 0 5px 0;'>{row['exam_name']}</h3>
                                </div>
                            </div>
                        </div>""", unsafe_allow_html=True)
                        if st.button("查看报告详情 >", key=f"view_{row['id']}"):
                            st.session_state['archive_view'] = 'detail'
                            st.session_state['selected_report_id'] = row['id']
                            st.rerun()

            elif st.session_state.get('archive_view') == 'detail':
                if st.button("⬅️ 返回报告列表"): st.session_state['archive_view'] = 'list'; st.rerun()
                    
                row = df[df['id'] == st.session_state['selected_report_id']].iloc[0]
                st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
                st.markdown(f"<h2>{row['exam_name']}</h2>", unsafe_allow_html=True)
                st.markdown(f"<p style='color:#86868b;'>学科：{row['subject']} &nbsp;|&nbsp; 归档时间: {row['scan_date']}</p>", unsafe_allow_html=True)
                
                c1, c2, c3 = st.columns(3)
                c1.metric("综合得分", row['total_score']); c2.metric("客观分", row['obj_score']); c3.metric("手阅分", row['subj_score'])
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(f"✨ 召唤 AI 导师点评", type="primary"):
                    with st.spinner("AI 导师正在思考..."):
                        comment = generate_ai_comment(student_name, row['subject'], row['total_score'], row['obj_score'], row['subj_score'])
                        st.success(f"💡 **AI 专属寄语**：\n\n{comment}")
                
                st.markdown("---")
                st.markdown("##### 📝 详细得分明细")
                if row['details']:
                    try: st.dataframe(pd.DataFrame(list(json.loads(row['details']).items()), columns=['题号', '得分']).T, use_container_width=True)
                    except: pass

                st.markdown("##### 📸 原卷批注留存")
                if row['exam_folder'] and os.path.exists(row['exam_folder']):
                    files = sorted(os.listdir(row['exam_folder']))
                    img_cols = st.columns(len(files) if len(files) < 4 else 4)
                    for i, file in enumerate(files):
                        with img_cols[i % 4]: st.image(f"{row['exam_folder']}/{file}", use_column_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------
# 模式四：📊 班级全景分析
# ------------------------------------------
elif mode == "📊 班级全景分析":
    st.markdown("<h1>Class Panorama.</h1>", unsafe_allow_html=True)
    analysis_exam = st.text_input("输入要检索的测评名称")
    if analysis_exam:
        df = pd.read_sql_query(f"SELECT student_id, student_name, obj_score, subj_score, total_score, details FROM results WHERE exam_name='{analysis_exam}'", sqlite3.connect("wenshan_cloud.db"))
        if not df.empty:
            st.metric("已归档人数", f"{len(df)} 份")
            flat_data = []
            for _, row in df.iterrows():
                base = {"学号": row['student_id'], "姓名": row['student_name'], "客观分": row['obj_score'], "主观分": row['subj_score'], "总分": row['total_score']}
                try: base.update(json.loads(row['details']))
                except: pass
                flat_data.append(base)
            flat_df = pd.DataFrame(flat_data)
            st.dataframe(flat_df, use_container_width=True)
            st.download_button("⬇️ 一键下载统分明细表", flat_df.to_csv(index=False), f"{analysis_exam}_成绩单.csv", type="primary")
        else: st.warning("暂无该测评的数据。")
