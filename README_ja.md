# gramide

コーディングエージェントのための構文木。[Almide](https://github.com/almide/almide) で書かれています。
`gramide` はソースファイルを、エージェントが問い合わせられる木にします。このファイルはまだパースできるか、
各宣言はどこから始まりどこで終わるか、このノードの名前は何か。文法は言語の普通の値で、パーサはそれを
解釈します。生成ステップも、エージェントと木の間に挟まるネイティブライブラリもありません。

[English](README.md)

```
gramide check   src/main.almd     パースできれば exit 0、失敗なら `file:line:col: unexpected X (expected …)`
gramide outline src/main.almd     宣言ごとに一行: L12-40 function_declaration parse
gramide parse   src/main.almd     木全体を S 式で
gramide tags    src/main.almd     `def function parse L40-58`、`ref call list.map L44`、`ref type Node L12` — リポジトリマップの入力
gramide tokens  src/main.almd     トークン列を一行ずつ
```

## なぜ

コードを編集するエージェントがパーサに求めるものは二つです。「いま壊したか」への速くて正直な答えと、
必要な部分だけ読むための「何がどこにあるか」の地図。コンパイラのフロントエンド全体は要らないし、
触る言語ごとに別のネイティブライブラリを要求すべきでもありません。gramide はその二つの答えを、
エージェントのツールと同じ言語で返す最小のものです。文法を他のモジュールと同じように読み、直し、
テストできます。

## 現状

2 言語: Almide（`.almd`）と Go（`.go`）。それぞれ参照コーパス全体で計測し、保証はどちらも同じで一方向です。
**gramide が拒否するファイルは参照パーサにとっても壊れている。** 逆は約束しません。既知の箇所で
コンパイラより寛容で、一覧は [docs/design.md](docs/design.md)。

**Almide** — Almide リポジトリの全 `.almd` ファイル（意図的に非 Almide 構文を試す 2 ディレクトリを除いた 3,382 ファイル）:

| ファイル | 結果 |
|---|---|
| 正しい 3,317 ファイル | すべてパース |
| `broken.almd` 診断フィクスチャ 65 | すべて拒否。いずれもコンパイラも拒否する |
| その他の `broken.almd` 720 | パースは通り、意図どおり型検査で落ちる |

**Go** — Go 1.27 の `GOROOT/src` 配下の全 `.go` ファイル（標準ライブラリ・コンパイラ・ツールチェーン、testdata 込みで 8,077 ファイル）:

| ファイル | 結果 |
|---|---|
| 8,042 ファイル | すべてパース |
| 35 ファイル（すべて `testdata`） | 拒否。いずれも `gofmt -e` も拒否する |
| `gofmt` が拒否する `testdata` 11 ファイル | パースは通る（ここでは gramide のほうが寛容） |

コーパス全体の `check` は 8 コアで Almide 2.5 秒、Go 23 秒。最大のファイル（11.6 万行の生成 Go ソース）単体で 7.6 秒。

## 仕組み

```
source ──lexer──▶ tokens ──parser(grammar)──▶ tree ──▶ check / outline / parse
```

- **`src/lexer.almd`** — バイト列上の手書き字句解析。改行はトークン（Almide は改行で文を区切る）、
  コメントと空行の連続は捨て、`${…}` 補間つき文字列・ヒアドキュメント・raw 文字列は一つのトークン。
- **`src/parser.almd`** — エンジン。文法は `Grammar { start, rules }` で、規則は `Rule` 値
  （`Tok`, `Lit`, `Seq`, `Alt`, `Rep`, `Opt`, `Wrap`, `Field`, `Left`, 先読み）。順序付き選択、
  貪欲な繰り返し、左再帰なし。二項演算子は `Left(kind, operand, op)` で、マッチ後に左畳み込み。
  パーサは失敗した最遠のトークンとそこで期待していたものを覚えていて、それが `check` の出すエラー。
- **`src/lang_almide.almd`**, **`src/lang_go.almd`** — 値としての文法。Go 文法は式の梯子を一つの関数から
  2 回（末尾の複合リテラルあり・なし）生成し、`if x == T{…} {` の曖昧さを避けています。
- **`src/lex_go.almd`** — Go の字句解析。セミコロン挿入はここで行い、文法は Go が区切りと見る場所にしか区切りを見ません。
- **`src/tree.almd`** — トークン添字で範囲を持つ `Node { kind, field, start, end, kids }` と、
  `child(n, "name")`, `text_of`, `sexp`, `collect`。

エンジンについて一つ。文法の値は起動時に 3 整数ノードの平坦な配列へコンパイルされ、`parse_rule` は
一つの自己再帰関数で、列・選択・繰り返しのループはその中にあります。どちらの形も Almide のネイティブ
バックエンドが値をコピーする仕方から来ていて、[docs/design.md](docs/design.md) に各規則とそれを強いた
計測を記録しています（最後の一つで 11.6 万行のファイルが 188 秒から 7.6 秒に）。

## ビルド

```
almide build            # → ./gramide
almide test             # 7 モジュール 20 テスト
```

Almide 0.61 以降が必要です。

## ライセンス

MIT または Apache-2.0、お好みで。
