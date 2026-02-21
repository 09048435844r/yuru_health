# Intake Logging 運用マニュアル

このドキュメントは、YuruHealth の「摂取ログ（Intake Logging）」機能を数ヶ月後に見返しても迷わず運用できるように、設定変更とデータ管理の実務手順をまとめたものです。

## 1. まず押さえるべきコア概念

### 1-1. GitOps 方式（設定UIは持たない）
- 摂取ログのマスターデータは **`config/supplements.yaml`** で一元管理します。
- Streamlit 画面上でマスターを編集する機能はありません。
- 変更は「YAML編集 → Gitコミット → Push → Cloud反映」で行います。

### 1-2. スナップショット保存（過去データが壊れない）
- 記録ボタン押下時に、当時の成分計算結果が `intake_logs.snapshot_payload`（JSONB）へ保存されます。
- その後に YAML を変更しても、**過去ログの JSONB は書き換わりません**。
- つまり「将来のレシピ変更」と「過去の摂取記録」は分離されており、安全です。

### 1-3. 量の定義は「1単位あたり」+「デフォルト数量」
- `items.<item_id>.ingredients` は **1単位あたりの成分量** を定義します。
- `items.<item_id>.unit_type` で単位（例: `錠`, `滴`, `回`）を指定します。
- `items.<item_id>.default_quantity` は UI 初期値（普段の摂取量）です。
- 製品推奨量を別フィールドで持たず、必要ならコメントで残します（例: `# 製品推奨: 2錠`）。

---

## 2. 実務 How-To

以下は、実際の運用でよく使う4パターンです。

### 2-1. 【プリセットの変更】Morning / Night のデフォルトON項目を変える

目的:
- ダッシュボードでシーン（Morning/Nightなど）を開いたとき、最初からチェックされる項目を変更する。

編集箇所:
- `config/supplements.yaml` の `presets.<Scene>.default_items`

#### 例: Morning から `vitamin_d3_k2_oil` を外す

変更前:
```yaml
presets:
  Morning:
    default_items:
      - blend_drink
      - vitamin_d3_k2_oil
```

変更後:
```yaml
presets:
  Morning:
    default_items:
      - blend_drink
```

ポイント:
- `default_items` には `items` のID（例: `blend_drink`）を指定します。
- IDの打ち間違いがあると、UIで期待どおりにONになりません。

---

### 2-2. 【成分量・配合の変更】特製ドリンクの成分値を更新する

目的:
- たとえば、イヌリンを 5g → 10g に変更する。

編集箇所:
- `config/supplements.yaml` の `items.<item_id>.ingredients`

#### 例: `blend_drink` の `イヌリン_g` を 5 から 10 に変更

変更前:
```yaml
items:
  blend_drink:
    name: "特製ブレンドドリンク"
    type: "base"
    unit_type: "回"
    default_quantity: 1
    ingredients:
      イヌリン_g: 5
      ビタミンC_mg: 1000
```

変更後:
```yaml
items:
  blend_drink:
    name: "特製ブレンドドリンク"
    type: "base"
    unit_type: "回"
    default_quantity: 1
    ingredients:
      イヌリン_g: 10
      ビタミンC_mg: 1000
```

ポイント:
- 値は必ず数値（int/float）で管理します（1単位あたり）。
- 単位はキー名に含める形式を維持します（例: `_mg`, `_g`, `_IU`）。

#### 参考: デフォルト数量だけを変える場合
```yaml
items:
  magnesium_doctors_best:
    name: "マグネシウム"
    type: "optional"
    unit_type: "錠"
    default_quantity: 3  # 実際の摂取量（製品推奨: 2錠）
    ingredients:
      マグネシウム_mg: 100
```

---

### 2-3. 【新しいサプリの追加（AI活用推奨）】

目的:
- 新しく購入したサプリを `items` に追加する。

編集箇所:
- `config/supplements.yaml` の `items`（必要なら `presets` も）

#### 推奨運用（最重要）
**成分表を手打ちしないこと。**
- サプリの成分表ラベル写真を Windsurf / Gemini に渡して、
- 「この成分表を YuruHealth の YAML 形式（`items`）に変換して」と依頼するのが最速・低ミスです。

依頼テンプレート例:
```text
この画像の成分表を、YuruHealth の supplements.yaml 形式に変換してください。
- values は数値のみ
- 単位はキー名に含める（例: ビタミンC_mg, ビタミンD_IU）
- item_id は英数字スネークケース
- type は base か optional
```

#### 追加例
```yaml
items:
  omega3_capsule:
    name: "オメガ3"
    type: "optional"
    unit_type: "ソフトジェル"
    default_quantity: 2
    ingredients:
      EPA_mg: 325
      DHA_mg: 225

presets:
  Night:
    default_items:
      - magnesium_doctors_best
      - omega3_capsule
```

ポイント:
- `item_id` は一意にする（重複禁止）。
- 先に `items` を追加し、その後 `presets` へ組み込むのが安全です。
- `ingredients` は「1単位あたり」に揃え、`default_quantity` で日常運用値を表現します。

---

### 2-4. 【製品リニューアル時の対応方針】2パターン

サプリの成分が変更されたときは、分析目的に応じて以下から選びます。

#### パターンA（連続性重視）
- 既存IDを維持し、`ingredients` の数値だけ上書き。
- ダッシュボード運用がシンプルで、日常の連続運用に向く。
- 過去ログはスナップショット保存なので安全。

例:
```yaml
items:
  multivitamin:
    name: "マルチビタミン"
    type: "optional"
    ingredients:
      ビタミンC_mg: 120   # 旧100から更新
      亜鉛_mg: 12          # 旧10から更新
```

#### パターンB（厳密な比較重視）
- `multivitamin_v2` のように新しいIDを作る。
- `presets.default_items` も旧IDから新IDへ差し替える。
- 「旧製品と新製品を完全に分離して比較したい」場合に最適。

例:
```yaml
items:
  multivitamin:
    name: "マルチビタミン（旧）"
    type: "optional"
    unit_type: "カプセル"
    default_quantity: 3
    ingredients:
      ビタミンC_mg: 100
      亜鉛_mg: 10

  multivitamin_v2:
    name: "マルチビタミン（新）"
    type: "optional"
    unit_type: "カプセル"
    default_quantity: 3
    ingredients:
      ビタミンC_mg: 120
      亜鉛_mg: 12

presets:
  Morning:
    default_items:
      - blend_drink
      - multivitamin_v2
```

判断基準:
- 日々の運用を簡単にしたい → **A**
- 製品切替前後を厳密比較したい → **B**

---

## 3. 変更時チェックリスト

YAML変更後は最低限これを確認:
- [ ] YAMLのインデント崩れがない（半角スペース）
- [ ] `default_items` のIDが `items` に存在する
- [ ] 成分値が文字列でなく数値になっている
- [ ] 単位がキー名に含まれている（`_mg`, `_g`, `_IU` など）
- [ ] 各 item に `unit_type` と `default_quantity` がある

---

## 4. デプロイフロー（最終手順）

`config/supplements.yaml` を保存したら、**Gitでコミット＆プッシュ**してください。  
通常、数分で Streamlit Community Cloud に自動反映されます。

例:
```bash
git add config/supplements.yaml
git commit -m "Update supplements presets and composition"
git push
```
