"""
Execution Policy Engine
Module: backend.open_webui.apps.workbench.security.policy
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import List, Optional, Tuple


class ExecutionMode(str, Enum):
    """
    Operational modes governing autonomous capabilities:
    - SAFE: Read-only inspection; all state-mutating actions are strictly blocked.
    - ASSISTED: Semi-autonomous; state-mutating actions require explicit user confirmation.
    - AUTONOMOUS: Full automated development loop; permitted workspace-confined mutations proceed without prompts.
    """
    SAFE = "SAFE"
    ASSISTED = "ASSISTED"
    AUTONOMOUS = "AUTONOMOUS"


class PolicyStatus(str, Enum):
    ALLOWED = "ALLOWED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class PolicyDecision:
    """Represents the evaluation verdict of an attempted action."""
    status: PolicyStatus
    mode: ExecutionMode
    action_type: str
    command_or_path: str
    reason: str
    risk_level: RiskLevel

    @property
    def is_allowed(self) -> bool:
        return self.status == PolicyStatus.ALLOWED

    @property
    def requires_confirmation(self) -> bool:
        return self.status == PolicyStatus.CONFIRMATION_REQUIRED

    @property
    def is_blocked(self) -> bool:
        return self.status == PolicyStatus.BLOCKED


class PolicyEngine:
    """
    Evaluates requested developer actions and commands against classified risk tiers
    and operational execution policies.
    """

    # 1. Permanently Forbidden Patterns: Blocked unconditionally regardless of execution mode.
    FORBIDDEN_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"\brm\s+-[rRfF]+\s+(/|\*|/\*)(\s+|$)", re.I), "Recursive root destruction"),
        (re.compile(r"\b(rmdir|rd)\b.*(/[sS]|/[qQ]).*[a-zA-Z]:\\?", re.I), "Root drive tree destruction"),
        (re.compile(r"\bformat\s+[a-zA-Z]:", re.I), "Disk formatting attempt"),
        (re.compile(r"\b(mkfs|fdisk|parted|diskpart)\b", re.I), "Disk partition or filesystem formatting"),
        (re.compile(r"\b(shutdown|reboot|init\s+[06]|poweroff|halt)\b", re.I), "System shutdown/reboot"),
        (re.compile(r"\bdd\s+if=.*of=(/dev/|\\\\.\\[a-zA-Z]:)", re.I), "Raw block device write attempt"),
        (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.I), "Fork bomb attempt"),
        (re.compile(r"\b(dump|save)\s+.*\\(SAM|SECURITY|SYSTEM)\b", re.I), "Windows registry credential hive dumping"),
        (re.compile(r"\bprocdump.*lsass\b", re.I), "LSASS memory credential dumping"),
        (re.compile(r"cat\s+.*(/etc/shadow|/etc/sudoers)", re.I), "Privileged credential file inspection"),
    ]

    # 2. Read-Only Patterns: Always permitted across SAFE, ASSISTED, and AUTONOMOUS modes.
    READ_ONLY_PATTERNS: List[re.Pattern] = [
        re.compile(r"^\s*(ls|dir|cat|head|tail|more|less|grep|rg|find|wc|stat|file|pwd)\b", re.I),
        re.compile(r"^\s*(git\s+(status|diff|log|show|branch|tag|remote|rev-parse))\b", re.I),
        re.compile(r"^\s*(python|node|npm|git|uv|cargo|rustc)\s+(--version|-v|-V)\b", re.I),
        re.compile(r"^\s*(which|where|where\.exe|echo|type)\b", re.I),
        re.compile(r"^\s*(Get-ChildItem|Get-Content|Select-String|Get-Item|Test-Path)\b", re.I),
    ]

    # 3. State-Mutating Patterns: Blocked in SAFE, Confirmation in ASSISTED, Permitted in AUTONOMOUS.
    STATE_MUTATING_PATTERNS: List[re.Pattern] = [
        re.compile(r"^\s*git\s+(add|commit|checkout|switch|merge|rebase|pull|push|stash|reset)\b", re.I),
        re.compile(r"^\s*(npm|pnpm|yarn|bun)\s+(install|ci|run|build|test|start)\b", re.I),
        re.compile(r"^\s*(pip|uv\s+pip)\s+(install|uninstall|sync)\b", re.I),
        re.compile(r"^\s*(pytest|vitest|jest|mocha|cargo|make)\b", re.I),
        re.compile(r"^\s*(python|node|bash|sh|powershell|cmd)\s+[^\s]+", re.I),
        re.compile(r"^\s*(mkdir|touch|rm|del|rmdir|cp|copy|mv|move)\b", re.I),
    ]

    def evaluate_action(
        self,
        mode: ExecutionMode,
        action_type: str,
        command_or_path: str,
    ) -> PolicyDecision:
        """
        Evaluates an action against the active execution policy.
        """
        cmd_clean = command_or_path.strip()
        action_lower = action_type.strip().lower()

        # Step 1: Check for permanently forbidden signatures
        for pattern, desc in self.FORBIDDEN_PATTERNS:
            if pattern.search(cmd_clean):
                return PolicyDecision(
                    status=PolicyStatus.BLOCKED,
                    mode=mode,
                    action_type=action_type,
                    command_or_path=command_or_path,
                    reason=f"Permanently forbidden command: {desc}",
                    risk_level=RiskLevel.CRITICAL,
                )

        # Step 2: Check for inherent read-only file actions
        if action_lower in ("read", "view", "list", "read_file", "list_dir"):
            return PolicyDecision(
                status=PolicyStatus.ALLOWED,
                mode=mode,
                action_type=action_type,
                command_or_path=command_or_path,
                reason="Read-only filesystem operation permitted.",
                risk_level=RiskLevel.LOW,
            )

        # Step 3: Check for read-only command patterns
        if action_lower == "execute":
            for pattern in self.READ_ONLY_PATTERNS:
                if pattern.search(cmd_clean):
                    return PolicyDecision(
                        status=PolicyStatus.ALLOWED,
                        mode=mode,
                        action_type=action_type,
                        command_or_path=command_or_path,
                        reason="Read-only inspection command permitted.",
                        risk_level=RiskLevel.LOW,
                    )

        # Step 4: Check for state-mutating actions (file writes, deletes, builds, test runs, scripts)
        is_mutating = (
            action_lower in ("write", "delete", "create", "modify", "write_file", "delete_file")
            or any(p.search(cmd_clean) for p in self.STATE_MUTATING_PATTERNS)
        )

        if is_mutating:
            if mode == ExecutionMode.SAFE:
                return PolicyDecision(
                    status=PolicyStatus.BLOCKED,
                    mode=mode,
                    action_type=action_type,
                    command_or_path=command_or_path,
                    reason="State-mutating action is prohibited under SAFE execution policy.",
                    risk_level=RiskLevel.HIGH,
                )
            elif mode == ExecutionMode.ASSISTED:
                return PolicyDecision(
                    status=PolicyStatus.CONFIRMATION_REQUIRED,
                    mode=mode,
                    action_type=action_type,
                    command_or_path=command_or_path,
                    reason="State-mutating action requires explicit user confirmation in ASSISTED mode.",
                    risk_level=RiskLevel.MEDIUM,
                )
            elif mode == ExecutionMode.AUTONOMOUS:
                return PolicyDecision(
                    status=PolicyStatus.ALLOWED,
                    mode=mode,
                    action_type=action_type,
                    command_or_path=command_or_path,
                    reason="State-mutating action permitted under AUTONOMOUS execution policy.",
                    risk_level=RiskLevel.MEDIUM,
                )

        # Step 5: Unclassified / default fallback
        if mode == ExecutionMode.SAFE:
            return PolicyDecision(
                status=PolicyStatus.BLOCKED,
                mode=mode,
                action_type=action_type,
                command_or_path=command_or_path,
                reason="Unclassified action blocked under SAFE mode.",
                risk_level=RiskLevel.HIGH,
            )
        elif mode == ExecutionMode.ASSISTED:
            return PolicyDecision(
                status=PolicyStatus.CONFIRMATION_REQUIRED,
                mode=mode,
                action_type=action_type,
                command_or_path=command_or_path,
                reason="Unclassified action requires user confirmation under ASSISTED mode.",
                risk_level=RiskLevel.MEDIUM,
            )
        else:
            return PolicyDecision(
                status=PolicyStatus.ALLOWED,
                mode=mode,
                action_type=action_type,
                command_or_path=command_or_path,
                reason="Action permitted under AUTONOMOUS mode.",
                risk_level=RiskLevel.LOW,
            )
