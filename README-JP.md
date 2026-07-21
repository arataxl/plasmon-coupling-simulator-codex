# Plasmonic Coupling Simulator

English version: [README.md](README.md)

金（Au）ナノ球のプラズモンカップリングを、結合双極子近似（CDA）と
量子補正モデル（QCM）で条件探索するための、研究者・学生向けローカルWebアプリです。
実験データの定量再現器や、BEM/DDA/FDTD/TDDFTの代替を目的にはしません。

> 状態：Phase 5まで実装済みです。Johnson and Christy材料データ、単一球の完全Mie参照計算、
> FCDA分極率、遅延 Green tensor、CDA中核、入力スキーマ、Validation Test 1〜3・5の
> 基礎試験に加え、Fig. 2d由来の暫定 `gamma_g` 表、局所誘電率、4層のCDA縮約、Test 4の
> 物理コア試験を実装済みです。同期 `POST /simulate` に加え、SSE進捗・協調的取消、
> 任意3D配置UI、CSV/JSONの正規化出力・JSON往復、Validation Test 6を実装しました。

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
| 直径 `40〜100 nm` | 高次多極子の影響があり得る。MVPでは粒径に応じた自動警告は未実装。 | 定性的・半定量的な探索用。BEM/DDA/FDTD等との比較を推奨。 |

Kreibig型サイズ補正は物理コアの検証用フックとしてのみ残し、MVPのAPI/UIからは
有効化できません。Esteban et al. (2012) にあるAu jellium・大波長域向けのDrude値は、
Johnson and Christy (1972) の実測バルク `n + ik` を基にするKreibig補正には転用しません。
一次資料との整合を確認して専用の受入試験を追加するまで、利用者向け機能として延期します。
Au光学定数はJohnson and Christy (1972)を用い、データ範囲外へ原則として外挿しません。

QCMの物理的根拠、暫定表の抽出方法、4層化の収束確認、限界は
[docs/quantum_corrected_model_integration.md](docs/quantum_corrected_model_integration.md) を正とします。

## 現在のアーキテクチャ

- **計算コア**：Mie参照計算、FCDA分極率、Green tensor、CDA、QCMを `src/physics/` に分離する。
- **API層**：FastAPI + uvicornの同期 `POST /simulate` と、ジョブ開始・取消・SSE配信を提供する。いずれも計算結果をサーバーへ永続保存しない。
- **サービス層**：`src/services/simulation_service.py` が単位変換、CDA/QCM実行、効率・来歴を含む応答メタデータの組立てを担う。`job_manager.py` はワーカースレッドで進捗と協調的取消を管理する。
- **SSE**：進捗イベントは波長点の点数だけを送り、スペクトルは完了イベントで一括返却する（D-1）。取消時は、現在の一波長計算が終わった境界で停止し、部分スペクトルを返却・保存しない。
- **UI**：静的HTML/CSS/Vanilla JavaScriptと、ローカル同梱のPlotly.jsを `web/` から同一オリジン配信する。設定は「粒子配置」「波長・入射条件」の2タブに分ける。QCMの適用範囲はギャップ入力横のツールチップとフッターで示し、QCMを適用した結果だけに出典・読取誤差・補間法などの詳細を表示する。日本語/Englishを切り替えられる。各球の径とx/y/z座標を個別編集でき、二量体・正三角形三量体・Test 5と同じ棄却サンプリングを使うランダムクラスタをプリセットとして持つ。プリセット座標はフォームへ反映する直前に0.1 nmへ丸め、丸め後も0.5 nm未満にならないことを確認する。
- **入出力**：CSVは波長、3種の断面積、3種の効率、集合体の幾何学的断面積を含む。JSONは入力、結果、QCM来歴、材料・モデル来歴を含む。ブラウザのCSV/JSONには、粒子数・径・3D配置・最小ギャップ・波長範囲・QCM適用有無・UTC時刻を付記し、ファイル名にも短縮条件を含める。正規化JSONはPydanticで再読込し、ブラウザ付加のダウンロード来歴を除いて同じ入力を再計算できる。ブラウザのダウンロードもサーバー保存を行わない。

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

既存Antigravity方針に従い、Plotly.js `2.24.1` は `web/vendor/` にローカル同梱しています。
取得元は `https://cdn.plot.ly/plotly-2.24.1.min.js`、期待SHA-256は
`d5dae4bdea4f17da17c819b04f7ddcf05e3cffd252194cbe89cbbff40ee1d3c7` です。
セットアップ実装時には、取得した資産のハッシュをこの値と照合してから配置します。

## セットアップ・起動

Python 3.12 のPython Launcherを利用します。初回は `setup_windows.bat` を実行し、
仮想環境と承認済み依存を作成します。Plotly.js同梱資産のSHA-256も検証します。
資産が欠けている場合だけ、公式CDNから取得します。セットアップ後の起動、計算、表示、
ブラウザへのCSV/JSONダウンロードはオフラインで完結します。

```powershell
setup_windows.bat
run_app.bat
```

起動後、<http://127.0.0.1:8000/> を開きます。`run_app.bat` は `127.0.0.1` にだけ
待ち受けます。

### APIの基礎

`POST /simulate` は `SimulationInput` を受け取り、基準波長の `cross_sections`（m²、効率付き）と、
波長範囲の `spectrum`（m²、効率付き）をJSONで返します。波長範囲は `spectrum` の
`start_wavelength_nm`、`end_wavelength_nm`、`step_nm` で指定します。同期APIでは計算時間を
抑えるため、返せる格子点数を301点以下に制限しています。

通常のUIは次の進捗付き経路を使います。

- `POST /simulate/jobs`：計算を開始し、`job_id` を返す。SSE版は最大5,000波長点まで受け付ける。
- `GET /simulate/stream/{job_id}`：波長点ごとの `progress`、最終の `complete`、取消時の `cancelled`、失敗時の `error` をSSEで返す。進捗には断面積などの部分データを含めない。
- `POST /simulate/jobs/{job_id}/cancel`：取消を要求する。SciPyの一波長線形ソルバーは安全のため途中で強制終了せず、次の波長点へ進む前に中断する。

UIの入力表は各粒子の径・x/y/z（nm）を最大20個まで編集でき、送信前にも全対の表面間
ギャップを検査します。0.5 nm未満は送信しません。0.5 nm以上1.0 nm未満の対はQCM自動適用を明示し、
1〜5 nmの対にはCDA近似限界の注意を表示します。

`0.5 ≤ gap < 1.0 nm` でQCMを自動適用した場合、`qcm_metadata` には
`provisional_digitized`、Fig. 2d、対象曲線、校正点未提供、読取誤差、補間法、層数、
CDA縮約の限界を必ず含めます。必要な来歴を構成できない場合は、成功結果や500エラーではなく
明示的なAPIエラーを返します。

## 検証方針

物理コアをUIより先にpytestで検証します。Test 1〜6は、単一球Mie、CDA孤立極限、
二量体結合、QCM安全装置、多粒子安定性、入出力再現性にそれぞれ対応します。
数値しきい値、QCMの4層/5層比較、Mie基準配列は
[docs/validation_plan.md](docs/validation_plan.md) と [docs/SPEC.md](docs/SPEC.md) を正とします。

Phase 2までにTest 1、入力スキーマ、Test 2、Test 3、Test 5の基礎pytestを実装済みです。
加えて、Test 4のうち、暫定 `gamma_g` 表、局所Drude誘電率、CDAへの4層縮約、5.439 Å境界、
3→4→5層感度を検証する物理コアpytestを実装済みです。QCM-CDA縮約は原論文のBEM/FEMと
等価ではなく、参考値の傾向探索に限ります。Test 4のAPI入力ブロックとQCMメタデータ応答は
`tests/test_api.py` で確認します。`tests/test_io_reproducibility.py` はCSV/JSONの完全一致、
効率定義、QCM来歴を含むJSON往復再計算を、`tests/test_api_sse.py` と
`tests/test_cancellation.py` はSSEの完了一括返却と取消時の部分データ非返却を確認します。
提出時には、実行環境・依存バージョン・pass実績を記録します。

## 人間・GPT-5.6・Codexの協働記録（Build Week提出用）

本プロジェクトでは、人間によるレビュー、GPT-5.6による分析、Codexによる実装を反復するサイクルを採用しました。AIの出力は物理的妥当性、実験値、文献上の主張の根拠として扱っていません。

GPT-5.6は、要件の分析、ブラウザテストで見つかった事項と監査結果の検討、横断的な整合性リスクの特定、実装計画の策定に使用しました。Codexは、承認済み変更の実装、テストとチェックの実行、文書の整備、検証結果の報告に使用しました。

| 人間の発見・判断 | Codexによる実装作業 |
| --- | --- |
| ブラウザテストで、プリセット座標の多桁小数が数値フォームへ入った後にスペクトル計算を妨げることが分かった。 | 表示用座標の丸め、丸め後のギャップ再検証、回帰テストを実装した。 |
| 人手レビューで、px固定の3Dマーカーではズーム時に実際の粒子径を把握できないことが分かった。 | 実径の`mesh3d`球、ラベル、等方軸スケール、描画上の安全策へ置き換えた。 |
| 監査で、QCM適用範囲と1〜5 nmの古典CDA警告の説明に不整合が見つかった。 | QCMとCDAの警告コードを構造化して分離し、日英UI翻訳、境界テスト、文書同期を行った。 |

人間は、実ブラウザでの問題発見、製品と物理スコープの選択、物理前提の承認、完成した挙動のレビューに責任を持ちました。GPT-5.6は、要件分析、監査結果の解釈、提案変更の優先順位付けを支援しました。Codexは、承認済み変更の実装、テストと文書の維持、検証結果の報告を担いました。

## 参照文書

- [docs/SPEC.md](docs/SPEC.md)：MVP仕様、優先順位、受入基準、提出期限
- [docs/physics_assumptions.md](docs/physics_assumptions.md)：物理前提と適用範囲
- [docs/quantum_corrected_model_integration.md](docs/quantum_corrected_model_integration.md)：QCM統合・暫定デジタイズ表の扱い
- [docs/validation_plan.md](docs/validation_plan.md)：Test 1〜6
- [docs/references.md](docs/references.md)：採用文献
- [LICENSE](LICENSE)：リポジトリ著作権者が作成したソースコード・文書に適用するMIT License
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)：第三者ソフトウェア、データ、論文資料に関する通知
