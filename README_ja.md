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
- **`src/incremental.almd`**、**`src/keystrokes.almd`** — パースしたファイルを、回復項目の中に
  回復項目が入れ子になった形で保持し、編集はそれが触れた最小の項目だけを読み直す
  ([docs/incremental.md](docs/incremental.md))。そして `reparse-bench` が回すキー入力ベンチ。
  各言語パッケージの tree-sitter ハーネスと同じ編集列を再生する。

## 編集の後にファイルを読む

パーサは `recover` / `recover_all` サイトが読んだノードにそのサイトの印を付ける。
`incremental.from_parsed` はそこで木を切り、各項目は自分のトークンだけを、子項目の間の
区間ごとに、区間の先頭からの相対位置で持つ。子の大きさは親の隣に並べておく。編集は、
それを丸ごと含む最も深い項目まで降り、その兄弟の窓を次のトークンまで字句解析し直し、
サイトの本体でそのトークンに届くまでパースし、新しい項目を差し込む。上の基準位置は
整数の和だけで決まる。字句解析かパーサが以前と食い違えば(窓の次のトークンが変わった、
窓がそこで終わらなかった)、答えは「全文を読め」になる。`ERROR` 項目の隣の編集も同じで、
回復は局所的でないからだ。結果は同じテキストの全文パースとトークン単位・ノード単位で
照合される。エンジンのテストと、各言語パッケージのコーパス上のランダム編集検証で。

TypeScript 5.9 の `compiler/checker.ts`(3.1 MB、うち 2.9 MB が 1 つの関数)で、識別子の
中への 1 キー入力は中央値 88 µs。tree-sitter の増分パースは 593 µs、全文パースは 58 ms
([gramide-typescript](https://github.com/O6lvl4/gramide-typescript) の
`docs/evidence/incremental-typescript-src.json`)。木全体が要る読み手は materialize する。
1 パスで、パースはしない。

何も読まない編集が 2 種類ある。コメントや空白の中の編集と、名前 1 つの打ち直しで、項目自身の
トークンの区間を字句解析し直して同じトークンが出ることを確かめ、位置だけ動かす。各項目は ID を
持ち、その項目に触れない編集では変わらない。自分の場所に読み直された項目も ID を保つ。各パッケージが
計測するファイルの 1,000 編集で ID が変わった項目はゼロだった(`reparse-bench` が数える)。同じ
読み手が Python にも効く。Python の文は `recover_lines` の項目で、単独で字句解析したスライスでは
インデントを置けないので、改行を打ちも消しもしていない編集では区間のレイアウトのトークンを
そのまま保つ。

## パースできないファイルを読む

recover site は item をそのまま試し、失敗したら 3 つの道のうち `ERROR` の下に入るトークンが
最も少ないものを取る。item 規則が次に読める位置までスキップする、欠けた `)` `]` `}` をファイル末尾に
あるものとして item を読み直す(編集で開いたままの本体を残せる)、失敗が最も遠くまで進んだ位置に
閉じ括弧を 1 つあるものとして読み直す(引数リストの `)` が消えたメソッドを丸ごと読める)。Python はレイアウト段で、
開いたままの括弧をインデントの浅い文が始まる行で閉じる。[docs/recovery.md](docs/recovery.md) が
その仕組みと計測で、各パッケージがコーパスの全ファイルを 4 通りに壊し、gramide と tree-sitter が
まだ列挙できる宣言を、それぞれの無傷のファイルでの列挙と比べる。「残った宣言」は列挙され続けた
宣言の割合、「きれいな破壊」は壊した箇所以外を失わず余計なものも出さなかった破壊の割合:

| コーパス | ファイル、破壊 | 残った宣言: gramide / tree-sitter | きれいな破壊: gramide / tree-sitter |
|---|---:|---:|---:|
| JavaScript, Node `lib/` | 427, 1,694 | 96.1% / 95.9% | 92.1% / 90.6% |
| TypeScript, TypeScript `src/` | 697, 2,588 | 98.2% / 99.0% | 95.2% / 94.6% |
| Go, Go `src/` | 8,010, 30,927 | 99.7% / 91.1% | 99.2% / 82.9% |
| Rust, Almide compiler `crates/` | 663, 2,632 | 99.9% / 97.5% | 99.8% / 94.9% |
| Python, CPython `Lib/` | 1,450, 5,193 | 98.9% / 96.3% | 98.1% / 82.3% |

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
にあります。言語ごとのコーパス、オラクル、tree-sitter との比較、キー入力ベンチは各言語のリポジトリにあります。

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
