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
gramide tokens  src/main.almd     トークン列を一行ずつ
```

## なぜ

コードを編集するエージェントがパーサに求めるものは二つです。「いま壊したか」への速くて正直な答えと、
必要な部分だけ読むための「何がどこにあるか」の地図。コンパイラのフロントエンド全体は要らないし、
触る言語ごとに別のネイティブライブラリを要求すべきでもありません。gramide はその二つの答えを、
エージェントのツールと同じ言語で返す最小のものです。文法を他のモジュールと同じように読み、直し、
テストできます。

## 現状

いまは Almide のみ。Almide リポジトリの全 `.almd` ファイル（意図的に非 Almide 構文を試す
2 ディレクトリを除いた 3,382 ファイル）で計測:

| ファイル | 結果 |
|---|---|
| 正しい 3,317 ファイル | すべてパース |
| `broken.almd` 診断フィクスチャ 65 | すべて拒否。いずれもコンパイラも拒否する |
| その他の `broken.almd` 720 | パースは通り、意図どおり型検査で落ちる |

コーパス全体の `check` は 8 コアで約 7 秒、1 ファイルあたり約 2 ms。

保証は一方向です。**gramide が拒否するファイルはコンパイラにとっても壊れている。** 逆は約束しません。
既知の箇所（比較演算子の連鎖、右辺が任意の `|>`、山括弧ジェネリクス、文字列のない `todo`）で
コンパイラより寛容で、`${…}` 補間の内側はパースしません。一覧は [docs/design.md](docs/design.md)。

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
- **`src/lang_almide.almd`** — 値としての Almide 文法。Almide リポジトリの `docs/GRAMMAR.md` に沿う。
- **`src/tree.almd`** — トークン添字で範囲を持つ `Node { kind, field, start, end, kids }` と、
  `child(n, "name")`, `text_of`, `sexp`, `collect`。

エンジンについて一つ。`parse_rule` は一つの自己再帰関数で、列・選択・繰り返しのループはその中にあります。
Almide のネイティブバックエンドがリスト引数を参照渡しにするのは、関数が相互再帰グループに属さないとき
だけです。補助関数に分けていたときは呼び出しのたびに文法とトークン列がコピーされ、280 行のファイルに
21 秒かかりました。インライン化した同じファイルは 0.15 秒です。

## ビルド

```
almide build            # → ./gramide
almide test             # 4 モジュール 15 テスト
```

Almide 0.61 以降が必要です。

## ライセンス

MIT または Apache-2.0、お好みで。
