from __future__ import annotations

from typing import Dict, Tuple, TypeAlias, Union

FileInfo: TypeAlias = Tuple[int, int, int]
TreeNode: TypeAlias = Union["TreeDict", FileInfo, None]
TreeDict: TypeAlias = Dict[str, TreeNode]
