# Hướng dẫn cập nhật và sử dụng dữ liệu ClassMarker

Tài liệu này mô tả cách cập nhật dữ liệu ClassMarker và cấu trúc hiện tại của hai file:

- `output/classmarker_data.json`
- `output/classmarker_questions.json`

## 1. Chuẩn bị môi trường

Chạy các lệnh từ thư mục gốc của project:

```bash
cd /Users/linhofthenorth/VietLinh/efms-project-info
source .venv/bin/activate
```

Thông tin đăng nhập, URL và selector được cấu hình trong `.env`. Session đăng nhập được lưu
tại `playwright/.auth/state.json`.

## 2. Quy trình cập nhật thông thường

Sau khi tài khoản ClassMarker có thêm bài mới (cả bài đã nộp có nút `Results`, lẫn bài chưa làm `Start` hoặc đang làm dở `Resume`), chạy lần lượt:

```bash
# Bước 1: cập nhật danh sách tất cả bài có Results, Start hoặc Resume
classmarker-crawl --format both --output output/classmarker_data

# Bước 2: crawl câu hỏi và đáp án của các URL mới (hỗ trợ cả Results và giao diện làm bài live)
classmarker-crawl-details

# Bước 3: tải các ảnh mới và cập nhật đường dẫn ảnh trong JSON
classmarker-download-images

# Bước 4 (tùy chọn): xuất bài thi và kết quả ra file PDF A4
classmarker-export-pdf
```

Kết quả:

```text
output/
├── classmarker_data.json
├── classmarker_data.csv
├── classmarker_questions.json
├── images/
│   ├── 10384784_xxxxxxxx.jpg
│   └── ...
└── pdfs/
    ├── Math Practice 1 - Student Name.pdf
    └── ...
```

`classmarker-crawl-details` sử dụng checkpoint theo `result_url`. Các bài đã có trong
`classmarker_questions.json` sẽ được giữ nguyên; crawler chỉ mở các URL mới. File được lưu
sau từng bài nên có thể chạy lại cùng lệnh nếu quá trình bị gián đoạn.

`classmarker-download-images` bỏ qua những ảnh đã tải thành công và chỉ tải ảnh còn thiếu.

## 3. Crawl lại toàn bộ câu hỏi

Nếu nội dung của những bài cũ đã thay đổi nhưng vẫn dùng cùng `result_url`, hãy backup file
hiện tại và crawl lại:

```bash
mv output/classmarker_questions.json output/classmarker_questions.backup.json
classmarker-crawl-details
classmarker-download-images
```

Sau khi kiểm tra dữ liệu mới thành công, có thể xóa file backup thủ công.

## 4. Tùy chọn hữu ích

```bash
# Hiện cửa sổ trình duyệt và tự đăng nhập/hoàn tất 2FA
classmarker-crawl --manual-login --headed

# Crawl chi tiết bằng phiên đăng nhập thủ công
classmarker-crawl-details --manual-login --headed

# Điều chỉnh thời gian nghỉ giữa các trang
classmarker-crawl-details --delay 1

# Điều chỉnh số luồng tải ảnh
classmarker-download-images --workers 8

# Xuất thử 1 bài PDF đầu tiên
classmarker-export-pdf --limit 1

# Xuất bài theo index hoặc tên bài thi
classmarker-export-pdf --test 0
classmarker-export-pdf --test "Bluebook Mini Verbal Test 1"

# Xuất đề thi trắng (không kèm đáp án và điểm) để in làm bài
classmarker-export-pdf --no-answers --output-dir output/pdfs/blank

# Xuất toàn bộ với số worker song song cao hơn
classmarker-export-pdf --workers 6
```

## 5. Cấu trúc `classmarker_data.json`

Top-level là một JSON array. Mỗi phần tử là một bài có nút `Results`:

```ts
type ClassMarkerData = ClassMarkerRow[];

interface ClassMarkerRow {
  Name: string;
  Percentage: string; // Ví dụ: "40%"
  Score: string;      // Ví dụ: "4 / 10"
  Duration: string;   // Ví dụ: "00:09:32"
  column_5: "Results";
  result_link: string;
}
```

Ví dụ:

```json
[
  {
    "Name": "Bluebook Mini Verbal Test 11Attempts allowed: 1",
    "Percentage": "40%",
    "Score": "4 / 10",
    "Duration": "00:09:32",
    "column_5": "Results",
    "result_link": "https://www.classmarker.com/test/results/?test_id=2284806"
  }
]
```

## 6. Cấu trúc `classmarker_questions.json`

Top-level là một JSON array. Mỗi phần tử chứa metadata của một bài và toàn bộ câu hỏi:

```ts
type ClassMarkerQuestions = TestResult[];

type QuestionStatus =
  | "correct"
  | "incorrect"
  | "partially_correct"
  | "unanswered"
  | "unknown";

interface TestResult {
  result_url: string;
  source_row: ClassMarkerRow;

  student_name: string;
  test_name: string;
  points_scored: number | null;
  points_available: number | null;
  percentage: number | null;
  duration: string;
  date_started: string;
  date_finished: string;

  questions: Question[];
}

interface Question {
  number: number;
  question_id: string;

  // Nội dung text thuần, phù hợp để tìm kiếm hoặc tạo preview.
  text: string;

  // Nội dung HTML, giữ định dạng, công thức, bảng và thẻ ảnh.
  html: string;

  // Đường dẫn ảnh local, tương đối từ thư mục output.
  images: string[];

  // URL ảnh gốc trên ClassMarker.
  source_images?: string[];

  points_scored: number | null;
  points_available: number | null;
  status: QuestionStatus;

  // Dùng cho câu multiple-choice.
  answers: AnswerOption[];
  selected_answers: AnswerOption[];
  correct_answers: AnswerOption[];

  // Dùng cho câu grid-in/free-text.
  answer_given: FreeTextAnswer | null;
  accepted_answers: AcceptedAnswer[];
}

interface AnswerOption {
  label: string; // Ví dụ: "A", "B", "C", "D"
  text: string;
  html: string;
  selected: boolean;
  correct: boolean;
  images: string[];
  source_images?: string[];
}

interface FreeTextAnswer {
  text: string;
  html: string;
  correct: boolean;
  images: string[];
  source_images?: string[];
}

interface AcceptedAnswer {
  text: string;
  html: string;
  images: string[];
  source_images?: string[];
}
```

## 7. Cách phân biệt loại câu hỏi

### Multiple-choice

```ts
if (question.answers.length > 0) {
  // Đáp án người dùng đã chọn
  const selected = question.answers.filter((answer) => answer.selected);

  // Đáp án đúng
  const correct = question.answers.filter((answer) => answer.correct);
}
```

`selected_answers` và `correct_answers` là các trường tiện dụng được tạo sẵn. Khi làm
frontend, nên ưu tiên `answers[].selected` và `answers[].correct` để render trong một vòng lặp.

### Grid-in hoặc free-text

```ts
if (question.answers.length === 0) {
  const submittedText = question.answer_given?.text;
  const acceptedTexts = question.accepted_answers.map((answer) => answer.text);
}
```

ClassMarker không luôn hiển thị accepted answer. Vì vậy `accepted_answers` có thể là mảng
rỗng, nhất là với một số câu trả lời sai. `answer_given` vẫn chứa câu trả lời đã nhập.

## 8. Liên kết hai file JSON

Khóa liên kết ổn định là URL kết quả:

```ts
row.result_link === testResult.result_url;
```

Ví dụ:

```ts
const detail = classmarkerQuestions.find(
  (test) => test.result_url === summaryRow.result_link,
);
```

Trong `classmarker_questions.json`, trường `source_row` đã chứa một bản sao của row tương
ứng từ `classmarker_data.json`. Frontend có thể chỉ tải file questions nếu không cần tối ưu
tốc độ tải danh sách ban đầu.

## 9. Đường dẫn ảnh

Sau khi chạy `classmarker-download-images`, dữ liệu có dạng:

```json
{
  "images": ["images/10384784_01BW3B80.png"],
  "source_images": [
    "https://0cm.classmarker.com/10384784_01BW3B80.png"
  ]
}
```

- `images`: đường dẫn local dùng cho frontend hoặc upload lên R2.
- `source_images`: URL ClassMarker gốc để đối chiếu.
- Thuộc tính `src` trong trường `html` cũng được chuyển sang `images/...`.

Khi upload lên R2, nên giữ nguyên cấu trúc:

```text
bucket-root/
├── classmarker_data.json
├── classmarker_questions.json
└── images/
    └── ...
```

Frontend có thể tạo URL tuyệt đối như sau:

```ts
const imageUrl = `${R2_BASE_URL}/${question.images[0]}`;
```

Khi render trường `html`, cần thay các `src="images/..."` bằng URL R2 tương ứng và sanitize
HTML bằng thư viện như DOMPurify trước khi đưa vào DOM.

## 10. Kiểm tra dữ liệu sau khi cập nhật

```bash
python -m json.tool output/classmarker_data.json > /dev/null
python -m json.tool output/classmarker_questions.json > /dev/null

pytest -q
ruff check src tests
```

Nếu các lệnh không báo lỗi thì hai file JSON hợp lệ và mã crawler đã vượt qua kiểm thử.
