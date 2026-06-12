"""Bitwise Classifier — 借鉴 Infinity IVC 的大类别高效分类

Infinity IVC (Infinite Vocabulary Classifier) 核心思路：
- 传统分类器: N 分类 → O(N×H) 参数量（N=2^32 时 8.8T 参数）
- IVC: N 分类 → d 个二分类 (d = log2(N)) → O(d×H) 参数（N=2^32 时仅 0.13M）
- 比特标签比类别标签对扰动更稳定

本项目将这一思想抽象为独立的 BitwiseClassifier，
用于大类别场景（如 prompt 质量评分、风格分类等）。
"""
import logging
import math
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


class BitwiseClassifier(nn.Module):
    """比特级分类器：将 N 分类拆解为 d 个二分类

    Args:
        embed_dim: 输入特征维度
        num_classes: 类别总数（将被自动拆解为 d = ceil(log2(num_classes)) 个二分类头）
        hidden_dim: 可选中间层维度（None 表示线性分类）
    """

    def __init__(self, embed_dim: int, num_classes: int, hidden_dim: Optional[int] = None):
        super().__init__()
        self.num_classes = num_classes
        self.num_bits = max(1, math.ceil(math.log2(num_classes))) if num_classes > 1 else 1
        self.bit_mask = (1 << self.num_bits) - 1  # 用于截断

        # 可选隐藏层
        if hidden_dim is not None and hidden_dim != embed_dim:
            self.project = nn.Linear(embed_dim, hidden_dim)
            self.act = nn.GELU()
            self.dropout = nn.Dropout(0.1)
            embed_dim = hidden_dim

        # d 个二分类头，每个输出 2 个 logits（0/1 两个比特）
        self.bit_heads = nn.ModuleList([
            nn.Linear(embed_dim, 2) for _ in range(self.num_bits)
        ])

        logger.info(
            "BitwiseClassifier: %d classes -> %d bits, "
            "traditional params: %d, bitwise params: %d",
            num_classes, self.num_bits,
            num_classes * embed_dim,
            self.num_bits * 2 * embed_dim,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, embed_dim) 输入特征

        Returns:
            logits: (B, num_bits, 2) 每个比特的二分类 logits
        """
        if hasattr(self, "project"):
            x = self.dropout(self.act(self.project(x)))

        bit_logits = []
        for head in self.bit_heads:
            bit_logits.append(head(x))  # (B, 2)
        return torch.stack(bit_logits, dim=1)  # (B, num_bits, 2)

    def decode(self, bit_logits: torch.Tensor) -> torch.Tensor:
        """将比特 logits 解码为类别索引

        Args:
            bit_logits: (B, num_bits, 2) 或 (num_bits, 2)

        Returns:
            class_indices: (B,) 解码后的类别索引
        """
        # 取概率最大类的比特
        bit_preds = bit_logits.argmax(dim=-1)  # (B, num_bits)
        # 将二进制转换为十进制
        result = torch.zeros(bit_logits.shape[0], dtype=torch.long, device=bit_logits.device)
        for i in range(self.num_bits):
            result += bit_preds[:, i] * (1 << i)
        # 截断到有效范围
        result = result.clamp(max=self.bit_mask)
        return result

    def loss(self, bit_logits: torch.Tensor, target_classes: torch.Tensor) -> torch.Tensor:
        """比特级交叉熵损失

        Args:
            bit_logits: (B, num_bits, 2)
            target_classes: (B,) 目标类别

        Returns:
            loss: 标量损失
        """
        # 将类别拆分为比特标签
        bit_targets = self._classes_to_bits(target_classes)
        # 对每个比特头计算交叉熵然后平均
        total_loss = 0.0
        for i in range(self.num_bits):
            target_bit = bit_targets[:, i]
            total_loss += F.cross_entropy(bit_logits[:, i], target_bit)
        return total_loss / self.num_bits

    def _classes_to_bits(self, classes: torch.Tensor) -> torch.Tensor:
        """将类别索引转换为比特张量

        Args:
            classes: (B,) 类别索引

        Returns:
            bits: (B, num_bits) 比特张量
        """
        bits = torch.zeros(classes.shape[0], self.num_bits, dtype=torch.long, device=classes.device)
        val = classes.clamp(max=self.bit_mask)
        for i in range(self.num_bits):
            bits[:, i] = val & 1
            val >>= 1
        return bits

    @classmethod
    def from_config(cls, embed_dim: int, num_classes: int) -> "BitwiseClassifier":
        """工厂方法：根据配置创建

        Args:
            embed_dim: 输入特征维度
            num_classes: 类别总数
        """
        hidden_dim = max(embed_dim // 2, 64)
        return cls(embed_dim, num_classes, hidden_dim=hidden_dim)
