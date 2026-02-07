from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseEvaluator(ABC):
    """
    健康データを評価するための抽象基底クラス
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    def evaluate(self, data: Dict[str, Any], mode: str = "logical") -> str:
        """
        健康データを評価してフィードバックを生成する
        
        Args:
            data: 評価対象の健康データ（weight_data, oura_data を含む辞書）
            mode: 評価モード（logical / witty）
            
        Returns:
            str: 生成されたフィードバックテキスト
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        評価機能が利用可能かどうかを確認する
        
        Returns:
            bool: 利用可能であれば True
        """
        pass
