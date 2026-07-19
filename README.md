# Plasmonic Coupling Simulator

金（Au）ナノ球のプラズモンカップリングを、結合双極子近似（CDA）と
量子補正モデル（QCM）で条件探索するための、研究者・学生向けローカルWebアプリです。
実験データの定量再現器や、BEM/DDA/FDTD/TDDFTの代替を目的にはしません。

> 状態：Phase 2完了。Johnson and Christy材料データ、単一球の完全Mie参照計算、
> FCDA分極率、遅延 Green tensor、CDA中核、入力スキーマ、Validation Test 1〜3・5の
> 基礎試験は実装済みです。API、UI、QCM、Test 4・6、セットアップ用バッチは未実装です。

## MVPで目指すこと

- Auナノ球1〜20個について、粒径、3D配置、表面間ギャップ、偏光、均一媒質を変え、
  Extinction、Scattering、Absorptionスペクトルの傾向を比較する。
- 単一球は完全Mie理論で参照し、多粒子系は遅延を含むdyadic Green tensorを使うCDAで計算する。
- QCMの対象では補正を自動適用し、適用範囲・警告・出典を隠さず表示する。
- Plotly.jsで結果を表示し、CSV/JSONとして再現可能な条件と結果を出力する。
- localhost限定・同一オリジン・通常動作時オフラインで利用する。

詳細な機能境界と受入基準は [docs/SPEC.md](docs/SPEC.md) を参照してください。

## 物理的な適用範囲と警告

内部計算はSI単位系で行い、UI/API/CSV/JSONの境界でnm等を変換します。MVPではAuの完全な球、
直径2〜100 nm、均一・等方・非吸収性媒質、波長200〜1500 nmを対象とします。

| 条件 | 動作 | 結果の扱い |
| --- | --- | --- |
| 表面間ギャップ `< 0.5 nm` | UIとAPIの双方で計算をブロックする。自動丸めはしない。 | 計算不可。接触・電荷移動プラズモン領域はMVPの対象外。 |
| `0.5 ≤ gap < 1.0 nm` | QCMを必ず自動適用する。ユーザーは無効化できない。 | Esteban et al. (2012) Fig. 2dのAu実線をデジタイズした暫定表を使う参考値。出典・校正・読取誤差・補間法・`provisional_digitized`をJSONとUIに明示する。 |
| `1.0 ≤ gap ≤ 5.0 nm` | 通常のCDAを使い、近似限界を警告する。 | 傾向探索・半定量的比較用。 |
| 直径 `≤ 40 nm` かつ `gap > 5 nm` | CDAの優先探索領域として扱う。 | それでも実験の定量再現を保証しない。 |
| 直径 `40〜100 nm` | 高次多極子の影響について警告する。 | 定性的・半定量的な探索用。 |

Kreibig型サイズ補正は既定でOFFです。有効時に517 nm未満を含む計算窓では、
帯間遷移との分離近似に関する警告を表示します。Au光学定数はJohnson and Christy (1972)を
用い、データ範囲外へ原則として外挿しません。

QCMの物理的根拠、暫定表の抽出方法、4層化の収束確認、限界は
[docs/quantum_corrected_model_integration.md](docs/quantum_corrected_model_integration.md) を正とします。

## 目標アーキテクチャ

- **計算コア**：Mie参照計算、FCDA分極率、Green tensor、CDA、QCMを `src/physics/` に分離する。
- **API/ジョブ層**：FastAPI + uvicornで計算開始、取消、結果取得を提供し、重い計算は別プロセスで管理する。
- **SSE**：進捗と取消状態だけを配信する。スペクトルは計算完了後に一括で表示し、取消時は部分結果を保存・出力しない。
- **UI**：静的HTML/CSS/Vanilla JavaScriptと、ローカル同梱のPlotly.jsを `web/` から同一オリジン配信する。
- **入出力**：CSVにはスペクトル列、JSONには再計算可能な入力・モデル・材料・QCMメタデータを保存する。

目標ディレクトリツリー、各層の責務、テスト対応、技術選定は
[docs/repository_structure.md](docs/repository_structure.md) に記載しています。

## 技術選定

| 領域 | 採用方針 |
| --- | --- |
| Web/API | FastAPI + uvicorn、`127.0.0.1`限定 |
| 数値計算 | NumPy + SciPy |
| 単一球Mie参照 | miepython（版と基準配列を固定して検証） |
| グラフ | ハッシュ検証済みのローカルPlotly.js。外部CDNは通常動作で使わない。 |
| スキーマ・入出力 | Pydantic、Python標準のJSON/CSV |
| テスト | pytest、`docs/validation_plan.md`のTest 1〜6に対応 |

実行依存は `requirements.txt`、開発依存は `requirements-dev.txt` に定義しています。
追加の依存パッケージ、バージョン変更、セットアップ手順の変更は、事前承認を得てから行います。

既存Antigravity方針に従い、Plotly.jsは `2.24.1` をローカルに同梱する予定です。
取得元は `https://cdn.plot.ly/plotly-2.24.1.min.js`、期待SHA-256は
`d5dae4bdea4f17da17c819b04f7ddcf05e3cffd252194cbe89cbbff40ee1d3c7` です。
セットアップ実装時には、取得した資産のハッシュをこの値と照合してから配置します。

## セットアップ・起動（実装後の予定）

実装後は、初回セットアップに `setup_windows.bat`、起動に `run_app.bat` を使う予定です。
初回だけ固定Python依存関係とPlotly.js資産の取得・SHA-256検証にネットワークが必要ですが、
セットアップ後の起動、計算、表示、CSV/JSON出力はオフラインで完結させます。

```powershell
setup_windows.bat
run_app.bat
```

この2ファイルは現時点では未作成です。実装前に、依存関係の承認とPlotly.js資産の
取得元・ハッシュの再確認を行います。

## 検証方針

物理コアをUIより先にpytestで検証します。Test 1〜6は、単一球Mie、CDA孤立極限、
二量体結合、QCM安全装置、多粒子安定性、入出力再現性にそれぞれ対応します。
数値しきい値、QCMの4層/5層比較、Mie基準配列は
[docs/validation_plan.md](docs/validation_plan.md) と [docs/SPEC.md](docs/SPEC.md) を正とします。

Phase 2までにTest 1、入力スキーマ、Test 2、Test 3、Test 5の基礎pytestを実装済みです。
Test 4・6とAPI/SSEの統合試験は後続Phaseで追加します。提出時には、実行環境・依存
バージョン・pass実績を記録します。

## 開発におけるAI利用記録（Build Week提出用）

AIの出力は物理的妥当性や文献値の証明ではありません。実際に利用した範囲、入力、
人手で行った確認を、提出時に事実に基づいて残します。

| ツール／モデル | 記録する内容 | 現時点の記録状態 |
| --- | --- | --- |
| Codex | 要件整理、文書整備、リポジトリ構成、テスト対応表の作成支援。物理的な適用範囲は既存docsと一次資料確認に従い、人が最終承認する。 | この設計文書整備で利用。 |
| GPT-5.6 | 利用した場合は、具体的な用途、入力の種類、生成物、人手の検証手順、採用・不採用の判断を記録する。利用していない場合は「未使用」と記載する。 | 実利用の有無・用途は提出前に記入が必要。 |

## 参照文書

- [docs/SPEC.md](docs/SPEC.md)：MVP仕様、優先順位、受入基準、提出期限
- [docs/physics_assumptions.md](docs/physics_assumptions.md)：物理前提と適用範囲
- [docs/quantum_corrected_model_integration.md](docs/quantum_corrected_model_integration.md)：QCM統合・暫定デジタイズ表の扱い
- [docs/validation_plan.md](docs/validation_plan.md)：Test 1〜6
- [docs/references.md](docs/references.md)：採用文献
