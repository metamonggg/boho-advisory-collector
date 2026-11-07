# 보호나라 보안공지 JSON 수집기

보호나라 RSS에서 보안공지를 가져와 제목, CVE, 영향을 받는 제품·버전, 대응 방법 등을 JSON으로 정리합니다. 데이터베이스나 LLM은 사용하지 않습니다.

## 실행

Python 3.10 이상에서 의존성을 설치합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

RSS에 올라온 공지를 가져옵니다.

```bash
python -m boho_rss
```

처음 몇 건만 가져오거나 설정 파일을 지정할 수도 있습니다.

```bash
python -m boho_rss --limit 3
python -m boho_rss --config config.json
```

실행 결과는 JSON 배열로 표준 출력에 표시되고, 공지별 JSON 파일은 `output/articles/<게시글ID>.json`에 저장됩니다. 같은 공지를 다시 수집하면 해당 파일을 새 결과로 덮어씁니다. 파싱이나 요청이 실패하면 오류를 표시하고 종료 코드 1을 반환합니다.

프로그램을 실행하면 전체 파싱 결과가 `output/articles/<게시글ID>.json`에 저장됩니다. 이 로컬 실행 결과에는 원문 본문 텍스트도 포함되며 GitHub에는 올리지 않습니다.

수집 결과를 보고 싶다면 공개 공지에서 추출한 구조화 정보 예시를 [output/examples/](output/examples/)에서 확인할 수 있습니다. 이 스냅샷에는 CVE, 제품·버전, 참고 링크가 들어가며 원문 설명 문단과 전체 본문은 제외했습니다. 필드 형태만 빠르게 확인할 수 있도록 [간단한 JSON 예시](examples/sample_advisory.json)도 제공합니다.

## JSON 형식

각 공지는 다음 정보를 담습니다.

- 게시글 ID, 제목, 게시일, 원문 URL
- 개요, 취약점 설명, CVE 번호와 취약점 종류
- 제조사, 제품명, 영향받는 버전 원문과 범위, 해결 버전 또는 조치
- 대응 방법, 참고 링크, 본문 텍스트
- 검토 필요 여부와 확인할 경고 목록

제품과 CVE는 원문 표의 같은 행에 함께 적혀 있을 때만 연결합니다. 원문에서 찾지 못한 값은 만들어내지 않고 경고로 남깁니다.

`affected_version`과 `fixed_version_or_action`에는 공지의 원문을 그대로 보존합니다. 각각 `affected_version_range`와 `fixed_version_range`에는 해석 가능한 `이상·초과·이하·미만` 조건을 `minimum`과 `maximum`으로 나눠 저장합니다. `inclusive`는 경계 버전을 포함하는지 나타냅니다. 해결 문구가 버전만 포함하고 연산자를 생략했더라도, 그 버전이 영향 범위의 exclusive maximum과 정확히 같으면 해결 최소 버전으로 저장합니다. 제품별 버전 비교 규칙까지 확인했다는 뜻은 아닙니다. 해석할 수 없는 문구는 `status: "needs_review"`, 원문이 없으면 `status: "not_provided"`로 남깁니다.

예를 들어 영향받는 버전 `9.0.47 이상 9.0.123 미만`은 `minimum: {"version": "9.0.47", "inclusive": true}`와 `maximum: {"version": "9.0.123", "inclusive": false}`가 되고, 해결 기준 `9.0.123 이상`은 `fixed_version_range.minimum`에 저장됩니다. 제품·배포판별 버전 비교는 별도 규칙이 필요하므로 이 결과만으로 자산의 취약 여부를 확정하지 않습니다.

## 설정

[`config.json`](config.json)에서 RSS 주소, JSON 출력 폴더, 요청 제한 시간과 재시도 횟수를 설정합니다. 상대 경로는 설정 파일이 있는 폴더를 기준으로 합니다.

## 프로젝트 구조

```text
.
├── boho_rss/
│   ├── __main__.py       # 명령줄 실행, 결과 JSON 출력
│   ├── article.py        # 공지 HTML에서 분석용 데이터 추출
│   ├── collector.py      # RSS 수집, 상세 페이지 요청, JSON 저장
│   ├── http_client.py    # HTTP 요청, 재시도, 요청 간격, 상세 URL 보정
│   ├── models.py         # RSS 공지 데이터 형식
│   ├── rss.py            # RSS XML 파싱
│   └── settings.py       # config.json 읽기와 설정 검증
├── output/
│   ├── articles/         # 실행 후 로컬에 생성되는 전체 결과 (Git 제외)
│   └── examples/         # 공개용 구조화 결과 예시
├── examples/
│   └── sample_advisory.json # 결과 JSON 형식 예시
├── config.json           # RSS 주소, 출력 폴더, 요청 설정
└── requirements.txt      # Python 외부 패키지
```

수집 흐름은 `__main__.py`에서 시작해 `collector.py`가 RSS 항목마다 상세 페이지를 요청하고, `article.py`가 필요한 내용을 파싱한 뒤 `output/articles/`에 JSON으로 저장하는 순서입니다.
