import fitz  # PyMuPDF
import os
from dotenv import load_dotenv
from openai import OpenAI
import json
import re  # 정규 표현식을 사용하기 위해 추가

# 환경 변수 로드
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def extract_text_from_pdf(pdf_path):
    """PDF에서 텍스트 추출 및 표지 구분"""
    doc = fitz.open(pdf_path)
    pages = [page.get_text("text") for page in doc]
    # 첫 페이지를 제목이나 표지로 인식하도록 설정
    title_page = pages[0] if len(pages) > 0 else "No Title"
    main_text = "\n\n".join(pages[1:])  # 본문은 표지를 제외한 나머지
    return title_page, pages, main_text

def determine_structure_based_on_length(num_pages, total_text_length):
    """PDF 분량에 따라 적절한 섹션과 토픽 개수 설정"""
    if num_pages <= 2 or total_text_length < 1000:
        return 1, 1  # 소량 자료: 섹션 1~2개, 서브토픽 1~2개
    elif 3 <= num_pages <= 5 or 1000 <= total_text_length < 3000:
        return 3, 2  # 중간 분량 자료: 섹션 3~5개, 서브토픽 2~3개
    else:
        return 5, 3  # 다량 자료: 섹션 5개 이상, 서브토픽 3~4개
    
def gpt_summarize(text, prompt, max_tokens=30):
    client = OpenAI(
        api_key=OPENAI_API_KEY
)
    
    """GPT를 사용하여 특정 지시에 맞는 요약 생성"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "user",
                "content": f"{prompt}\n\n{text}"
            }
        ],
        max_tokens=max_tokens,  # 섹션 요약을 위해 적절히 조정
        temperature=0.5
    )

    result = response.choices[0].message.content.strip()
    
    # "A: B" 형식에서 "A"를 제거하고 "B"만 반환
    result = re.sub(r"^[^:]+:\s*", "", result)
    
    return result

def find_page_range(subtopic_title, pages):
    """subtopic과 연관된 페이지 범위를 찾는 함수"""
    start_page, end_page = None, None
    for i, page_text in enumerate(pages):
        if subtopic_title in page_text:
            if start_page is None:
                start_page = i + 1  # 1부터 시작하는 페이지 번호
            end_page = i + 1
    return start_page or 1, end_page or start_page

def parse_pdf_as_roadmap(pdf_path):
    """PDF 전체를 요약하여 로드맵 형태로 JSON 생성"""
    title_page, pages, entire_text = extract_text_from_pdf(pdf_path)
    num_pages = len(pages)
    total_text_length = len(entire_text)

    max_sections, max_subtopics = determine_structure_based_on_length(num_pages, total_text_length)

    title = gpt_summarize(title_page, "Extract the title of this document, avoiding generic terms like 'Introduction' or 'Core Concepts'.", max_tokens=20)
    overall_summary = gpt_summarize(entire_text, "Summarize the main purpose and key topics of this document without using terms like 'Overview' or 'Core Concepts'.", max_tokens=50)

    roadmap_sections = {}
    for i in range(1, max_sections + 1):
        title = gpt_summarize(entire_text, f"Identify a concise title for main topic #{i}, focusing on core concepts.", max_tokens=20)
        if not title or title in roadmap_sections:
            continue
        description = gpt_summarize(entire_text, f"Summarize the topic '{title}' in one concise sentence. avoiding words like 'Overview' or 'Core'.", max_tokens=30)
        
        subtopics = []
        for j in range(1, max_subtopics + 1):
            subtopic_title = gpt_summarize(entire_text, f"Provide a concise title for subtopic #{j} under '{title}, avoiding generic terms.'", max_tokens=20)
            if subtopic_title.startswith("Subtopic #") or subtopic_title in [sub['title'] for sub in subtopics]:  # 불필요한 접두어 제거 및 중복 검출
                subtopic_title = re.sub(r"^Subtopic #\d+\s*-\s*", "", subtopic_title)
            subtopic_details = gpt_summarize(entire_text, f"Describe '{subtopic_title}' in one concise sentence.", max_tokens=30)

            # 페이지 범위 추정
            page_start, page_end = find_page_range(subtopic_title, pages)
            page_range = f"{page_start}-{page_end}" if page_start != page_end else f"{page_start}"
            
            # 학습 목표 생성 (필요한 핵심 목표 1~3개)
            learning_objectives_text = gpt_summarize(
                entire_text,
                f"Summarize 1 to 3 core learning objectives for '{subtopic_title}' in brief, clear statements.",
                max_tokens=100
            )

            # 숫자나 접두어 제거 후 배열로 변환
            checkpoints = re.split(r'\d+\.\s*', learning_objectives_text)
            checkpoints = [obj.strip() for obj in checkpoints if obj.strip()]

            subtopics.append({
                "title": subtopic_title,
                "details": [subtopic_details],
                "checkpoints": checkpoints,
                "page_range": page_range  # 페이지 범위 추가
            })

        roadmap_sections[title] = {
            "title": title,
            "description": description,
            "subtopics": subtopics
        }

    json_structure = {
        "title": title if title else "Document Title Not Found",
        "overall_summary": overall_summary,
        "sections": list(roadmap_sections.values())
    }

    return json_structure

# pdf file 입력
pdf_path = "./pdfs/Lecture4_AI.pdf"
output_json = parse_pdf_as_roadmap(pdf_path)

# JSON 파일로 저장
with open("result.json", "w", encoding="utf-8") as f:
    json.dump(output_json, f, indent=4, ensure_ascii=False)

print("Successful")

