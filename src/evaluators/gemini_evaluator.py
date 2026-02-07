import yaml
import json
from typing import Dict, Any, Optional
from pathlib import Path
from src.evaluators.base_evaluator import BaseEvaluator

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class GeminiEvaluator(BaseEvaluator):
    """
    Google Gemini APIを使用した健康データ評価クラス
    """
    
    def __init__(self, config: Dict[str, Any], secrets_path: str = "config/secrets.yaml", 
                 settings_path: str = "config/settings.yaml", prompts_path: str = "config/prompts.yaml", 
                 model_name: Optional[str] = None):
        super().__init__(config)
        self.secrets_path = Path(secrets_path)
        self.settings_path = Path(settings_path)
        self.prompts_path = Path(prompts_path)
        self.api_key = self._load_api_key()
        self.model_name = model_name or self._load_model_name()
        self.prompts = self._load_prompts()
        self.model = None
        self._initialize_model()
    
    def _load_api_key(self) -> Optional[str]:
        """Gemini APIキーを読み込む"""
        try:
            with open(self.secrets_path, "r", encoding="utf-8") as f:
                secrets = yaml.safe_load(f)
                return secrets.get("gemini", {}).get("api_key")
        except Exception:
            return None
    
    def _load_model_name(self) -> str:
        """設定ファイルからモデル名を読み込む"""
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)
                return settings.get("gemini", {}).get("model_name", "gemini-1.5-flash")
        except Exception:
            return "gemini-1.5-flash"
    
    def _load_prompts(self) -> Dict[str, str]:
        """プロンプトテンプレートを読み込む"""
        try:
            with open(self.prompts_path, "r", encoding="utf-8") as f:
                prompts_data = yaml.safe_load(f)
                return prompts_data
        except Exception as e:
            print(f"Failed to load prompts: {e}")
            return {
                "logical": {
                    "template": "健康データを分析してください：{weight_summary}\n{oura_summary}"
                },
                "witty": {
                    "template": "健康データをユーモアを交えて分析してください：{weight_summary}\n{oura_summary}"
                }
            }
    
    def _initialize_model(self):
        """Geminiモデルを初期化する"""
        if GENAI_AVAILABLE and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
            except Exception:
                pass
    
    def is_available(self) -> bool:
        """評価機能が利用可能か確認"""
        return GENAI_AVAILABLE and self.model is not None and self.api_key is not None
    
    def evaluate(self, data: Dict[str, Any], mode: str = "logical") -> str:
        """
        健康データを評価してフィードバックを生成
        
        Args:
            data: 評価対象の健康データ
            mode: 評価モード（logical / witty）
            
        Returns:
            str: 生成されたフィードバックテキスト
        """
        if not self.is_available():
            return "⚠️ Gemini APIが利用できません。APIキーを設定してください。"
        
        prompt = self._build_prompt(data, mode)
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"❌ 評価中にエラーが発生しました: {str(e)}"
    
    def _build_prompt(self, data: Dict[str, Any], mode: str) -> str:
        """
        評価用プロンプトを構築
        
        Args:
            data: 健康データ
            mode: 評価モード
            
        Returns:
            str: 構築されたプロンプト
        """
        weight_summary = self._format_weight_data(data.get("weight_data", []))
        oura_summary = self._format_oura_data(data.get("oura_data", []))
        
        if mode not in self.prompts:
            raise ValueError(f"Unknown mode: {mode}")
        
        template = self.prompts[mode].get("template", "")
        
        return template.format(
            weight_summary=weight_summary,
            oura_summary=oura_summary
        )
    
    def _format_weight_data(self, weight_data: list) -> str:
        """体重データを整形"""
        if not weight_data:
            return "体重データ: なし"
        
        latest = weight_data[0] if weight_data else None
        if latest:
            return f"""体重データ:
- 最新体重: {latest.get('weight_kg', 'N/A')}kg ({latest.get('measured_at', 'N/A')})
- 直近7日平均: {self._calculate_average(weight_data[:7], 'weight_kg'):.1f}kg
- データ件数: {len(weight_data)}件"""
        return "体重データ: 利用可能なデータなし"
    
    def _format_oura_data(self, oura_data: list) -> str:
        """Ouraデータを整形"""
        if not oura_data:
            return "Ouraデータ: なし"
        
        latest = oura_data[0] if oura_data else None
        if latest:
            return f"""Oura Ringデータ:
- 活動スコア: {latest.get('activity_score', 'N/A')}点
- 睡眠スコア: {latest.get('sleep_score', 'N/A')}点
- コンディションスコア: {latest.get('readiness_score', 'N/A')}点
- 歩数: {latest.get('steps', 'N/A')}歩
- 測定日: {latest.get('measured_at', 'N/A')}
- データ件数: {len(oura_data)}件"""
        return "Oura Ringデータ: 利用可能なデータなし"
    
    def _calculate_average(self, data: list, key: str) -> float:
        """平均値を計算"""
        values = [item.get(key, 0) for item in data if item.get(key) is not None]
        return sum(values) / len(values) if values else 0
