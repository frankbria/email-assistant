=============================================================================== tests coverage ================================================================================ 
______________________________________________________________ coverage: platform win32, python 3.10.11-final-0 _______________________________________________________________ 

| Name                                 | Stmts | Miss | Branch | BrPart | Cover | Missing                                  |
|---------------------------------------|-------|------|--------|--------|-------|-------------------------------------------|
| app\api\routers\tasks.py              | 43    | 22   | 10     | 1      | 45%   | 36, 44-76                                |
| app\dependencies.py                   | 13    | 13   | 6      | 0      | 0%    | 2-30                                     |
| app\main.py                           | 54    | 3    | 4      | 2      | 91%   | 36, 77->exit, 80-81                      |
| app\middleware.py                     | 17    | 2    | 2      | 1      | 84%   | 24-25                                    |
| app\models\assistant_task.py          | 33    | 4    | 8      | 4      | 80%   | 25, 31, 41, 44                           |
| app\services\action_suggester.py      | 61    | 5    | 24     | 3      | 91%   | 26, 35, 68->73, 77-79, 130->136          |
| app\services\ai_client.py             | 42    | 23   | 8      | 2      | 42%   | 24-25, 54-90                             |
| app\services\context_classifier.py    | 18    | 5    | 2      | 1      | 70%   | 26-31                                    |
| app\services\email_summarizer.py      | 48    | 15   | 16     | 3      | 66%   | 17-30, 35-50, 89->97, 92-94, 108         |
| app\services\task_classifier.py       | 12    | 1    | 4      | 1      | 88%   | 77                                       |
| app\strategies\action_registry.py     | 15    | 0    | 2      | 1      | 94%   | 15->17                                   |
| app\utils\email_utils.py              | 30    | 3    | 14     | 3      | 86%   | 10, 31, 46                               |
| **TOTAL**                             | 512   | 96   | 116    | 22     | 78%   |                                           |

6 files skipped due to complete coverage.

### Short Test Summary Info

- **FAILED** `tests/test_services/test_email_task_mapper.py::test_full_mapping_and_defaults` - AssertionError: assert 'Forward' in ['Reply', 'Archive', 'Delete']
- **Result:** 1 failed, 33 passed, 43 warnings in 27.10s
