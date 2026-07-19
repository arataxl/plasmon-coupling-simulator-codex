# QCM統合指示書

## 目的
粒子間表面ギャップが1 nm未満の領域において、電子トンネル効果を
無視した古典的CDA/Green tensorモデルが示す非物理的な発散
（電場増強の無限大化、消光断面積の異常な増大）を抑制するため、
Quantum Corrected Model（QCM）を計算コアに統合する。

## 採用する理論的根拠
本実装は、以下の文献で提案されたQCMをそのまま採用する。
独自の数値・パラメータを新規に導出・捏造しない。

- Esteban, R.; Borisov, A. G.; Nordlander, P.; Aizpurua, J.
  "Bridging quantum and classical plasmonics with a
  quantum-corrected model."
  Nature Communications 3, 825 (2012).
  DOI: 10.1038/ncomms1806

原論文本文の「Quantum plasmonics in large metallic systems」節は、半径25 nmの
Au球を `epsilon_inf = 1`、`hbar * omega_p = 7.9 eV`、
`hbar * gamma_p = 0.09 eV` のDrudeモデルで記述する。この記述はAu jellium・
大波長域向けで、2.0 eV以上で重要となる帯間遷移を含まない。これらは原論文の
QCM例における材料設定として記録するものであり、Johnson and Christy (1972) の
バルク `n + ik` を基にするFCDA/Kreibig補正のパラメータとして転用しない。
本タスクでは距離依存パラメータ表、局所誘電率、4層のギャップ離散化、および既存
CDAへの補助双極子としての注入までを実装する。原論文と同じBEM/FEMによる局所場の
完全解ではなく、CDAに合わせた縮約近似であることを本書の「CDAへの縮約」で明記する。

## QCM距離依存パラメータの情報源（D-2確定）

- Esteban et al. (2012) の公式Supplementary Information（Supplementary
  Figures S1--S2およびSupplementary Discussion、全5ページ）を再確認した。
  Supplementary Figure S1 はNa二量体について指数関数の接続点を変えた
  頑健性検証であり、`l' = 11.76 a.u.`、`14.76 a.u.`、`5.46 a.u.` は
  いずれもNaの例である。Supplementary Figure S2もNa二量体のTDDFT/QCM比較である。
- Supplementary Discussionは大型Au球とbowtie antennaでも同様の頑健性を支持する
  と述べるだけで、Auに用いる指数関数の係数、Au向けのフィット手順、数値表、
  または生データは示していない。Naの数値をAuへ流用してはならない。
- よって、Supplementary InformationにAuの `gamma_g(l)` 数値表またはFig. 2dを
  再構成できる詳細なAu数値があるという根拠は確認できず、D-2の結論は変更しない。
- よってMVPでは、**原論文Fig. 2dのAu jelliumに対応する青色の実線**を
  デジタイズした表を暫定参照表として採用する。青色の白丸（SSTM値）は
  表の値として採用せず、曲線読取りの補助情報としてのみ扱う。

### 暫定デジタイズ表の抽出・記録

1. DOI `10.1038/ncomms1806` の公式PDFにあるFig. 2dを原図として固定し、
   取得日、ファイル識別情報、対象曲線（Au jellium・青色実線）を記録する。
2. 横軸・縦軸ごとに、両端のラベル付き目盛を主校正点、残りのラベル付き目盛を
   検証点として画像座標と物理座標の対応を求める。軸の目盛形式は原図の表示に従い、
   校正点の値とピクセル座標を抽出記録へ残す。
3. 曲線の中心線を読み取り、各点の画像座標、変換後の `l` と `gamma_g`、
   および補間方法を表に保存する。表の有効範囲外へは外挿しない。現在の
   `data/qcm/gamma_g_au_digitized.csv` は、利用者提供のWebPlotDigitizer手動読取り
   22点を版管理した暫定表である。
4. 各軸の読取誤差は、未使用の検証目盛に対する校正残差と曲線線幅の半分を
   ピクセル単位で合成し、軸変換後の `delta_l` と `delta_gamma_g` として
   各表または抽出記録に残す。数値の桁数はこの誤差を超えて主張しない。現在の
   表には校正点記録が提供されていないため、`data/qcm/metadata.yaml` にその不足を
   明記し、読取誤差は利用者提示の5--10%目安だけを保存する。

### 暫定値であることの明示

- `src/physics/qcm.py` には「暫定値：Esteban et al. (2012) Fig. 2dのAu実線を
  デジタイズした参照表。原著者のAu係数表ではない」と明記済みである。
- `src/physics/qcm.py` は `log(gamma_g)` に対するPCHIP補間、局所誘電率、環状層の
  離散化、CDA補助双極子の構成を担う。表の上限を超えた場合は値を外挿せず古典極限を
  返す。
- JSONメタデータには少なくとも `qcm_parameter_source`、
  `qcm_parameter_status`（`provisional_digitized`）、`qcm_figure`、
  `qcm_curve`、`qcm_calibration_points`、`qcm_reading_uncertainty`、
  `qcm_interpolation` を保存する。これらと層数・CDA縮約モデル・誤差注記を必須化する
  `src/schemas/result.py` は実装済みである。JSON出力・UI注記の実装は別タスクとする。

## モデルの物理的な考え方
QCMは、粒子間ギャップを「空の媒質」としてそのまま扱うのではなく、
ギャップ内に「トンネル電流を模した架空の導電性媒質」を配置し、
これを通常のDrudeモデルの枠組みで扱う手法である。
古典的手法とフルの量子力学的計算（TDDFT）の橋渡しとして機能する。

## 実装すべき数式（文献の式番号に対応）

1. 通常のDrude誘電関数（式1）：
   epsilon(omega) = epsilon_inf - omega_p^2 / (omega^2 + i*omega*gamma_p)

2. ギャップ内の架空媒質の静的コンダクタンス（式5、SSTM近似）：
   sigma_0(l) は、ギャップ幅 l の関数として、電子トンネル
   透過確率 T(l) から積分計算される。本ツールでは、上記のD-2決定に従い、
   Fig. 2dのAu実線をデジタイズした暫定参照表から gamma_g(l) を与える。

3. トンネル減衰定数の指数関数近似（原論文の背景）：
   gamma_g(l) は l -> 0 で gamma_g(0) = gamma_p（バルク金属の
   減衰定数）に収束し、大きな l では急速に**増大**する指数関数形を取る。
   その結果、等価媒質の静的導電率は大きな `l` で急速に減衰する。
   境界条件（l=0でgamma_p、透過率T(l')=0.01となる特定のl'で
   SSTM計算値に一致）が原論文で示されている。ただしAu係数とフィット手順を
   一次資料で固定できないため、MVPではこの指数関数を独自に再構成しない。

4. ギャップ内の架空媒質の誘電関数（式3）：
   epsilon(l, omega) = 1 - omega_g^2 / (omega^2 + i*omega*gamma_g(l))
   ここで omega_g = omega_p（バルク金属のプラズマ周波数）とする。

   本プロジェクトでは、真空なら上式をそのまま使う。water等の均一・非吸収性媒質では、
   Faraday Discussions 178, 151--183 (2015) の式(19)に従う媒質基線を用い、

   epsilon_g(l, omega) = epsilon_medium
                           - omega_p^2 / [omega (omega + i gamma_g(l))]

   とする。これは、同式(19)のうちデジタイズ表と一次資料で固定できる自由電子Drude項
   だけを残した形である。Auのd電子減衰長は今回の暫定表に対して校正されていないため
   追加しない。Faraday Discussions論文は、Au二球の局所QCMではこのd電子項を省いても
   主なextinction・近接場スペクトルを本質的には変えないと報告するが、本MVPのCDA縮約の
   定量精度を保証するものではない。

   `omega_p` はEsteban et al. (2012)のAu jellium例に記載された
   `hbar * omega_p = 7.9 eV` を `omega_p = E / hbar` でrad/sへ換算して用いる。
   `hbar * gamma_p = 0.09 eV` は同じQCM例の接触極限の記録としてメタデータに残すが、
   現在の実装はFig. 2dの `gamma_g(l)` 表を直接使うため、別途その値へ置換しない。
   これらをJohnson and ChristyのFCDA/Kreibigパラメータとして転用しないという既存の
   制約は維持する。

## 適用範囲と切り分け（本ツール独自の運用ルール）
文献のQCMは連続的な距離依存モデルだが、本ツールでは以下のように
離散的な運用ルールとして適用する。

- gap < 0.5 nm：計算をブロックする（QCMの適用範囲外として扱う）。
  文献のFig. 3, 4でもD<0.5 Å（接触・重なり領域）は
  QCMではなく別の扱い（contact regime, CTPモード）が必要であり、
  本ツールの多粒子CDA枠組みでは対応しない。
- 0.5 nm <= gap < 1 nm：QCMを自動適用する（tunnelling regime）。
- gap >= 1 nm：QCMを適用せず、通常のCDAで計算する
  （non-contact regime、文献のD>5 Å相当の領域概念を1 nmに
  読み替えて運用する）。

  ※ 文献の非接触領域の目安（D>5 Å、すなわち0.5 nm）と、
  本ツールが設定した「QCM適用の上限（1 nm）」は一致しない。
  これは意図的な安全マージンであり、文献の知見をそのまま
  数値流用したものではないことをコード内コメントとREADMEに明記する。

## 実装上の要求

### 原論文のシェルとCDAへの縮約

- 原論文は、中心軸に垂直な面で局所幅 `l(rho)` が異なるギャップを同心環状シェルに
  分割し、各シェルへ `epsilon_g(l_i, omega)` を与えてBEM/FEMでMaxwell方程式を解く。
  原論文の典型的な収束値は8層である。
- 本MVPでは二球の中心間軸について、
  `l(rho) = d_c - sqrt(R_1^2-rho^2) - sqrt(R_2^2-rho^2)` を使う。ここで `d_c` は
  中心間距離、`R_1`, `R_2` は半径である。Fig. 2d表の上限以内の円形領域を、等投影面積の
  **4層**の環状体積へ分ける。各層の代表幅は環状面積の中点で評価する。
- 既存CDAは各Au球を一つの双極子で表すため、環状シェルをそのまま未知数にできない。
  各層の体積 `V_i` と局所誘電率 `epsilon_i` を、背景媒質 `epsilon_m` 中の体積等価小球の
  Clausius--Mossotti分極率

  `alpha_i = 3 epsilon_0 epsilon_m V_i (epsilon_i-epsilon_m)
             / (epsilon_i + 2 epsilon_m)`

  へ写像する。`sum_i alpha_i` を最接近点の中点に置く一つの補助ブリッジ双極子とし、Au球の
  双極子と同じ遅延Green tensor連立方程式・断面積計算へ含める。これはDraine & Flatau (1994)
  の離散双極子/体積分割の考え方を、原論文の環状シェルへ最小限に適用した追加近似である。
- `0.5 <= gap < 1.0 nm` ではQCM選択状態を自動適用する。ただしFig. 2d表の最終点
  `5.439... Å`（約0.544 nm）を超える局所幅には値を外挿しない。この場合、該当対は
  `epsilon_g = epsilon_medium`、すなわち補助双極子なしの古典極限となる。これは0.544〜1.0 nm
  で「QCMを無効化した」のではなく、D-2で確定した非外挿方針を適用した結果である。

### 4層採用と誤差の扱い

- gap 0.5、0.7、0.9 nmの同一径二量体、軸平行偏光で、3→4層を感度確認、4→5層を
  合否判定として比較する。`C_ext`、`C_sca`、`C_abs`の各スペクトル最大値で正規化した差と
  ピーク高さ差は1%以下、ピーク位置差は波長刻み以下を実務上の目安とする。
- 実装は各計算で `max_i |epsilon_i-epsilon_m|/epsilon_m` を記録する。この弱コントラスト指標を
  `eta` とすると、同位置に縮約した層間の自己無撞着応答を捨てる一次体積積分近似の局所的な
  高次項はおおむね `O(eta^2)` である。これは**補助双極子の局所近似成分だけ**の目安であり、
  曲率、少数双極子CDA、Au jellium表、d電子項省略を含む総合誤差の上限ではない。
- 原論文のBEM/FEMまたは独立DDA参照との比較は未実施である。したがって本縮約モデルの
  形状・局所場に由来するモデル形式誤差は現時点で定量上界を与えられず、結果は参考値に限る。
  3/4/5層比較に合格しても、原論文と同等の収束・精度を意味しない。
- 原論文はBEM計算で典型的に8層まで収束させており、4層はMVP向けの近似である。
  4→5層で基準を満たさない場合は4層を採用しない。
- QCM適用時も、既存のCDA（多粒子dyadic Green tensor）の方程式形と線形ソルバーは維持する。
  ただし補助双極子を含めるぶん、未知数はQCM対象対ごとに最大3自由度増える。
- QCM適用の有無、適用したパラメータ（omega_p, gamma_p, 層数 n）、
  および上記の暫定デジタイズ表の出典・校正・読取誤差・補間法を
  計算結果のメタデータ（JSON）に必ず記録する。

## 検証要求
- validation_plan.mdのTest 4（極小ギャップの安全装置とQCM適用）に
  従い、gap=0.5〜1.0 nmの範囲でQCM適用前後のスペクトル変化が
  文献Fig. 3, 4に示される定性的傾向（電場増強の抑制、
  モード間の連続的な遷移）と矛盾しないことを確認する。
- 文献の数値そのもの（Na jelliumモデルの結果等）と完全一致する
  ことは初版では要求しない。定性的な傾向の一致を確認基準とする。
- 暫定デジタイズ表を使う場合は、表の有効範囲、読取誤差、
  `provisional_digitized` の状態を検証結果とメタデータに明示する。

## 明記すべき限界（README・UI双方に反映）
- 本QCM実装は、球対称ギャップに対するSSTM（static scanning
  tunnelling microscopy）近似に基づくものであり、原論文が示す
  Na/Auジェリウムモデルでの厳密なTDDFT検証結果とは異なる
  可能性がある。
- Auの距離依存パラメータは原論文Fig. 2dのデジタイズ値であり、
  著者提供の係数表または生データではない。したがって結果は暫定値として扱い、
  表の補間・読取誤差による不確かさを含む。
- 帯間遷移（interband transitions, 2.0 eV以上）の影響は、
  文献同様、本モデルのAuパラメータ（omega_p, gamma_p）には
  含まれていない。QCM適用領域と帯間遷移域（波長517 nm未満）が
  重複する場合は、既存のKreibig補正警告と合わせて二重に
  警告表示する。
