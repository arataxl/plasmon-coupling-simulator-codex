# 参照資料

## 初版で使う根拠

1. Mie理論
   - Bohren, C. F.; Huffman, D. R.
     Absorption and Scattering of Light by Small Particles.
   - 用途：単一球のExtinction、Scattering、Absorptionの定義と参照解

2. Au光学定数
   - Johnson, P. B.; Christy, R. W.
     Optical Constants of the Noble Metals.
     Physical Review B 6, 4370–4379 (1972).
   - 用途：Auのバルク複素屈折率 n, k
   - 注意：ナノ粒子そのものではなく、バルク由来の光学定数である

3. CDA、遅延 Green tensor、断面積
   - Draine, B. T.; Flatau, P. J.
     Discrete-dipole approximation for scattering calculations.
     Journal of the Optical Society of America A 11, 1491–1499 (1994).
     DOI: 10.1364/JOSAA.11.001491
   - 用途：Phase 2 の遅延 dyadic Green tensor、CDA連立方程式、
     Extinction/Scattering/Absorption の SI 表現の根拠
   - 注意：初版の高速CDA計算へDDSCATを直接組み込まない

4. 有限サイズ分極率とKreibig補正
   - Meier, M.; Wokaun, A.
     Enhanced fields on large metal particles: dynamic depolarization.
     Optics Letters 8, 581–583 (1983).
     DOI: 10.1364/OL.8.000581
   - 用途：有限サイズ球における動的脱分極と放射減衰の位置付け
   - Kreibig, U.; Vollmer, M.
     Optical Properties of Metal Clusters.
     Springer Series in Materials Science 25, Springer (1995).
     DOI: 10.1007/978-3-662-09109-8
   - 用途：サイズ依存緩和率 `gamma_R = gamma_bulk + A v_F / R`。
     AuのDrudeパラメータは本リポジトリで独自に仮定しない。

5. BEMによる精密参照
   - Hohenester, U.; Trügler, A.
     MNPBEM – A Matlab toolbox for the simulation of plasmonic nanoparticles.
     Computer Physics Communications 183, 370–381 (2012).
   - 用途：将来的なナノスター、ナノキャップ、少数粒子系の精密検証
   - 注意：初版の必須依存関係にはしない

6. 量子補正モデル（QCM）
   - Esteban, R.; Borisov, A. G.; Nordlander, P.; Aizpurua, J.
     Bridging quantum and classical plasmonics with a quantum-corrected model.
     Nature Communications 3, 825 (2012).
     DOI: 10.1038/ncomms1806
   - 用途：サブナノメートルの粒子間ギャップにおけるトンネル効果を、
     等価的な局所誘電応答として古典電磁場計算へ組み込むQCMの理論的根拠
   - 注意：本ツールでの適用範囲と距離しきい値は、原論文の数値を
     そのまま流用せず、`docs/physics_assumptions.md` と
     `docs/quantum_corrected_model_integration.md` の運用ルールに従う
   - 一次資料確認：本文「Quantum plasmonics in large metallic systems」は、
     Au jellium・大波長域向けの `epsilon_inf = 1`、
     `hbar * omega_p = 7.9 eV`、`hbar * gamma_p = 0.09 eV` を記載する。
     これは帯間遷移を含まないQCM例の設定であり、Johnson and Christy (1972) の
     バルク `n + ik` を使うKreibig補正の値としては採用しない。
   - Supplementary Information（Supplementary Figures S1--S2、
     Supplementary Discussion）には、Auの `gamma_g(l)` 数値表、Au係数、
     Au向けフィット手順は確認できない。
   - Esteban, R.; Zugarramurdi, A.; Zhang, P.; Nordlander, P.; García-Vidal,
     F. J.; Borisov, A. G.; Aizpurua, J.
     A classical treatment of optical tunneling in plasmonic gaps: extending the
     quantum corrected model to practical situations.
     Faraday Discussions 178, 151--183 (2015).
     DOI: 10.1039/C4FD00196F
   - 用途：任意の背景媒質へのQCM拡張（式19）、局所ギャップ幅に応じた環状シェルの
     実装、Au局所QCMにおけるd電子項省略の位置付け。本文のAuパラメータ
     `hbar omega_p = 9.065 eV`、`hbar gamma_p = 0.0708 eV` は別の経験的
     フィットであり、本MVPのFig. 2d暫定表・2012年のAu jellium設定へ混在させない。

7. 物理定数
   - NIST, CODATA Recommended Values of the Fundamental Physical Constants:
     2022, NIST SP 961 (2024).
     https://physics.nist.gov/cuu/pdf/wall_2022.pdf
   - 用途：`hbar = 6.582119569...e-16 eV s` を用いた、エネルギー表示の
     Drudeパラメータから角周波数（rad/s）への変換。
