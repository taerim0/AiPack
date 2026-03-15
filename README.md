# AiPack
폴더와 내부 파일들을 single binary data로 (계층유지) -> ai가 읽기 쉽게

```cpp
python cli.py pack /* 패킹할 폴더 경로 */ /* 결과물 경로 및 파일명.aip */
//--compression none <-- 압축 없음
//--compression zstd <-- Zstandard 압축

python cli.py list /* aip 파일 */


python cli.py info /* aip 파일 */


python cli.py tree /* aip 파일 */


python cli.py cat /* aip 파일 */ /* 목표 파일의 경로 및 파일명 */


python cli.py extract /* aip 파일 */ /* 언패킹 위치 폴더 */


python cli.py extract-one /* aip 파일 */ /* aip 파일 내부 단일파일 */ /* 언패킹 위치 폴더 */
```



확장?

cli package

compression

streaming dataset

multimodal dataset format?

embedding

vector search

dataset versioning