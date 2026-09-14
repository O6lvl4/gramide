# gramide

コーディングエージェントのための構文木。[Almide](https://github.com/almide/almide) で書かれています。
これはそのエンジンです。バイト列の字句解析器、文法「値」を解釈するパーサ、構文木、その上の読み手
（outline・tags・構造化 symbols・リポジトリマップ・括弧バランス検査）、そしてライブラリとしての
コマンドライン。ここに言語はありません。言語は独立したパッケージで、このエンジンに値をひとつ
渡すだけ。バイナリ — みんなが実行する `gramide` コマンドは
[gramide-cli](https://github.com/O6lvl4/gramide-cli) です — は、そのパッケージのうち自分が
合成したものです。

[English](README.md)

```
gramide                 このリポジトリ: エンジン・契約・読み手・コマンドライン
gramide_almide   .almd       言語ごとに 1 リポジトリ。それぞれがエンジンに依存する
gramide_go       .go         https://github.com/O6lvl4/gramide-go
gramide_rust     .rs         https://github.com/O6lvl4/gramide-rust
gramide_python   .py .pyi    https://github.com/O6lvl4/gramide-python
gramide-cli                  `gramide` コマンド: 上の全パッケージを 1 ファイルで合成
```

tree-sitter と同じ形（ランタイム・文法ごとのリポジトリ・CLI）です。違いは言語が強いる一点だけ。
Almide は静的リンクなので、バイナリは実行時にロードするのではなく自分の `main.almd` で
出荷する言語を名指しします。そのため各言語パッケージも小さな自前バイナリを持ち、他の言語なしに
テスト・計測・再生成できます。

## 中にあるもの

```
source ──lexer──▶ tokens ──parser(grammar)──▶ tree ──▶ outline / symbols / tags / map
```

- **`src/lex.almd`** — 表で記述できる言語すべてで共用する字句解析器。パッケージが渡すのは
  `Spec`。キーワード、演算子、コメント記号、改行の意味、そして表では書けない 2 つ（数値の
  書き方と文字列の終わり方）の族の指定。Go は spec 32 行です。
- **`src/parser.almd`** — エンジン。文法は `Rule` 値（`Tok`, `Lit`, `Seq`, `Alt`, `Rep`, `Opt`,
  `Wrap`, `Field`, `Left`, 先読み, 回復）からなる `Grammar { start, rules }`。順序付き選択、
  貪欲な繰り返し、左再帰なし。値は一度だけ 3 整数ノードの平坦な配列にコンパイルされ、実行時は
  何もコンパイルせず、パッケージがコミットした表を読みます。失敗した最遠のトークンを覚えていて、
  それが `check` の出すエラー。読み手は失敗したら回復モードで読み直し、諦めた部分には `ERROR`
  ノードが立ちます。
- **`src/tree.almd`**, **`src/names.almd`** — トークン添字で範囲を持つ
  `Node { kind, field, start, end, kids }`。kind と field はひとつの名前表への番号。
- **`src/package_api.almd`** — 契約。`Definition` と `SymbolRules`。
  [docs/language-packages.md](docs/language-packages.md) がその全部です。
- **`src/registry.almd`**, **`src/lang.almd`** — ホスト。定義のリストを受け取り、
  `Reading`（木、回復済みかどうか、パッケージが名前について言うこと）を返します。
- **`src/tags.almd`**, **`src/symbols.almd`**, **`src/map.almd`**, **`src/balance.almd`** — 読み手。
  ファイルごとの定義と参照、hew が読むバージョン付き JSON（[docs/symbols.md](docs/symbols.md)）、
  予算内に収めたリポジトリの地図、文法のない言語にも与えられる括弧バランス検査。
- **`src/cli.almd`** — 全コマンドをライブラリとして。バイナリは `Program` を合成して `run` を
  呼ぶだけ。バイナリ自身が書くのは複数ファイルの並列 `check` だけで、その理由はそこに記録して
  あります。
- **`src/tables.almd`** — コンパイル済み文法を Almide ソースとして書き下す。各パッケージの
  `src/table.almd` はこれで作られます。

## 言語パッケージを書く

```
gramide-go/
  almide.toml        name = "gramide_go"。依存は gramide だけ
  src/mod.almd       definition()
  src/lexer.almd     Spec、または自前のスキャナ
  src/grammar.almd   fn rules() -> parser.Grammar とそのテスト
  src/symbols.almd   symbol_rules(): どのノードが名前を宣言し、メソッドを持ち、型に言及するか
  src/table.almd     生成物: `./gramide_go gen-table > src/table.almd`
  cli/main.almd      パッケージ自身のバイナリ、20 行
  ci/check.sh        almide test、表の一致検査、バイナリのスモーク、その言語のオラクル
```

[docs/language-packages.md](docs/language-packages.md) が各ファイルを説明します。
`src/package_contract_test.almd` は 40 行の完全なパッケージ（架空の構文に自前の字句解析・文法・
規則）で、エンジン自身のテストと `ci/smoke.py` がそれを全コマンドに通します。

## バイナリを合成する

```
import gramide.cli
import gramide_go

fn packages() -> List[package_api.Definition] = [gramide_go.definition()]

effect fn main() -> Unit = {
  let argv = env.args()
  match cli.batch_of(argv) {
    some((cmd, paths)) => cli.report(parallel(cmd, paths)!),   // fan ブロックで 8 スライス
    none => cli.run(cli.Program { name: "mine", version: "0.1.0", packages: packages() }, argv),
  }
}
```

[gramide-cli](https://github.com/O6lvl4/gramide-cli) はまさにこれを 4 パッケージに対して
行ったものです。`parallel` はどのバイナリも持つ 20 行で、エンジン側に置けない理由は契約ページに
あります。

## 計測

[docs/design.md](docs/design.md) はエンジンの形を決めた各規則と、それを強いた計測を記録して
います（そのひとつで 11.6 万行の生成 Go ファイルが 188 秒から 7.6 秒に）。
[bench/README.md](bench/README.md) はその後のすべての性能変更の記録で、証拠は `docs/evidence/`
にあります。言語ごとのコーパス、オラクル、tree-sitter との比較は各言語のリポジトリにあります。

## ビルド

```
almide test          # 100 テスト。契約テストを含む
bash ci/check.sh     # 同上に加え、デモバイナリを全コマンドに通す
```

Almide 0.62 以降が必要です。パッケージからは次のように依存します。

```toml
[dependencies]
gramide = { git = "https://github.com/O6lvl4/gramide", tag = "v0.1.2" }
```

## ライセンス

MIT または Apache-2.0、お好みで。
