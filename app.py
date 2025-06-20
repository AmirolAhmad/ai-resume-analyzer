import streamlit as st
import openai
import docx2txt
import PyPDF2
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime
import io
import json
import re
import smtplib
from email.message import EmailMessage

def email_resume_file(file_bytes, filename):
    msg = EmailMessage()
    msg["Subject"] = "New Resume Uploaded"
    msg["From"] = os.getenv("EMAIL_SENDER")
    msg["To"] = os.getenv("EMAIL_RECEIVER")
    msg.set_content("A new resume has been uploaded.")

    msg.add_attachment(file_bytes, maintype="application", subtype="octet-stream", filename=filename)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.getenv("EMAIL_SENDER"), os.getenv("EMAIL_PASSWORD"))
        smtp.send_message(msg)

# --- Load .env key ---
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI()

def extract_text_from_pdf(uploaded_file):
    file_bytes = uploaded_file.read()  # Baca sekali
    email_resume_file(file_bytes, uploaded_file.name)  # Hantar salinan bytes

    uploaded_file.seek(0)  # Reset pointer untuk PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))  # Gunakan salinan
    return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])


def extract_text_from_docx(uploaded_file):
    return docx2txt.process(uploaded_file)

def get_job_suggestions_openai(resume_text):
    prompt = f"""
    You are a career advisor AI. Based on the following resume, suggest 3 specific job titles that best match the candidate's profile.
    Resume:
    ---
    {resume_text}
    ---
    Return only the job titles, one per line, no numbering or extra text.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100
    )
    result = response.choices[0].message.content
    return [line.strip() for line in result.splitlines() if line.strip()]

def get_skills_openai(resume_text):
    prompt = f"""
    You are an AI assistant. Extract and list the key technical and soft skills found in the following resume.
    Return the skills only, as a comma-separated list.

    Resume:
    ---
    {resume_text}
    ---
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150
    )
    result = response.choices[0].message.content
    return [skill.strip() for skill in result.split(",") if skill.strip()]

def classify_skills_with_ai(skill_list):
    skill_str = ", ".join(skill_list)
    prompt = f"""
    Classify the following skills into two categories: 'Technical Skills' and 'Soft Skills'.
    Return the result as JSON with two keys: 'technical' and 'soft'.

    Skills: {skill_str}
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You will return only valid JSON with two keys: 'technical' and 'soft'."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=800
    )

    content = response.choices[0].message.content.strip()
    content = re.sub(r"^```json\n?|```$", "", content).strip()

    try:
        result_json = json.loads(content)
        return result_json.get("technical", []), result_json.get("soft", [])
    except json.JSONDecodeError:
        st.error("❌ Failed to parse skills from GPT response.")
        st.write("Raw response from GPT:")
        st.code(content)
        return [], []

def create_export_data(resume_text, job_suggestions, skills):
    data = {
        "timestamp": datetime.now().isoformat(),
        "resume_snippet": resume_text[:300] + "...",
        "suggested_jobs": ", ".join(job_suggestions),
        "skills": ", ".join(skills)
    }
    return pd.DataFrame([data])

# --- Streamlit App ---
st.set_page_config(page_title="AI Resume Analyzer", layout="centered")
st.title("🧠 AI Resume Analyzer v1")
st.text("AI Resume Analyzer is a smart tool that helps users analyze and improve their resumes. It automatically extracts key skills, suggests suitable job titles, evaluates job fit, provides career path recommendations, and gives an overall resume score — all based on the content of the uploaded resume. This tool aims to boost your chances in job applications by making your resume more targeted, optimized, and professional.")

uploaded_file = st.file_uploader("Upload your Resume (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    if uploaded_file.name.endswith(".pdf"):
        resume_text = extract_text_from_pdf(uploaded_file)
    else:
        resume_text = extract_text_from_docx(uploaded_file)

    st.subheader("📋 Resume Preview")
    st.text_area("Extracted Text", resume_text, height=250)
    st.subheader("📊 Resume Score (AI-Powered)")
    with st.spinner("Evaluating resume quality..."):
        score_prompt = f"""
        You are an AI resume reviewer. Based on this resume, provide a score from 0 to 100 that reflects the overall quality of this resume for job applications.
        Consider formatting, clarity, relevance, and overall impression. Just return the number only without explanation.

        Resume:
        ---
        {resume_text}
        ---
        """
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": score_prompt}],
            max_tokens=10
        )
        score = response.choices[0].message.content.strip()
        st.metric(label="AI Resume Score", value=f"{score}/100")

    st.subheader("📈 Visual Skill Breakdown")
    with st.spinner("Analyzing visual skill..."):
        skills = get_skills_openai(resume_text)
        tech_skills, soft_skills = classify_skills_with_ai(skills)

        skill_data = pd.DataFrame({
            "Skill Type": ["Technical", "Soft"],
            "Count": [len(tech_skills), len(soft_skills)]
        })

        st.write("Detected Skills:")
        st.markdown(f"**🛠️ Technical Skills:** {', '.join(tech_skills) if tech_skills else 'None'}")
        st.markdown(f"**🤝 Soft Skills:** {', '.join(soft_skills) if soft_skills else 'None'}")
        st.bar_chart(data=skill_data, x="Skill Type", y="Count", use_container_width=True)

    st.subheader("💼 Suggested Job Roles")
    with st.spinner("Thinking..."):
        suggestions = get_job_suggestions_openai(resume_text)
        for job in suggestions:
            st.success(f"✅ {job}")

    st.subheader("📈 Career Path Suggestion")
    with st.spinner("Generating career path..."):
        career_prompt = f"""
        You are a career advisor AI. Based on the resume below, suggest a realistic career path progression.
        Include 3 to 5 stages with job titles, starting from current level and progressing to senior roles.

        Resume:
        ---
        {resume_text}
        ---
        """
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": career_prompt}],
            max_tokens=300
        )
        career_path = response.choices[0].message.content
        st.write(career_path)


    tab1, tab2 = st.tabs([
        "📄 JD Matching", "🧠 Resume Tips & Career Path"])

    with tab1:
        st.subheader("📄 Paste Job Description")
        job_desc = st.text_area("Job Description", placeholder="Paste full JD here...", height=200)

        if st.button("🔍 Match Resume with JD"):
            with st.spinner("Analyzing match..."):
                match_prompt = f"""
                Compare this resume with the following job description. Return:
                1. Match percentage (%)
                2. Matched skills/keywords
                3. Missing important skills or requirements

                Resume:
                {resume_text}

                Job Description:
                {job_desc}
                """
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": match_prompt}],
                    max_tokens=300
                )
                result = response.choices[0].message.content
                st.markdown("### 🔎 Matching Results")
                st.write(result)

    with tab2:
        st.subheader("🧠 Resume Improvement Suggestions")
        if st.button("✨ Get AI Tips to Improve Resume"):
            with st.spinner("Analyzing and generating suggestions..."):
                tip_prompt = f"""
                You are a resume reviewer AI. Read this resume and provide 3 specific improvement suggestions to make it more attractive for job applications.

                Resume:
                ---
                {resume_text}
                ---
                """
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": tip_prompt}],
                    max_tokens=250
                )
                suggestions = response.choices[0].message.content
                st.markdown("### 🛠️ Suggestions to Improve Resume")
                st.write(suggestions)

st.markdown("---")
st.text("Author: Amirol Ahmad a.k.a xambitt | Email: xambitt@gmail.com")