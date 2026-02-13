import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime, timezone
import uuid

# Project imports
# Adjust path if needed, but pytest usually handles src/ discovery if configured right
from guardspine_local_council.council import LocalCouncil
from guardspine_local_council.types import ReviewRequest, ReviewVote

class TestCouncilSanitization(unittest.IsolatedAsyncioTestCase):
    async def test_council_redacts_prompt_before_provider_call(self):
        """Verify that PII in the review request is redacted before reaching the provider."""
        
        # 1. Setup Request with PII (Email)
        sensitive_code = "def send_mail():\n    recipient = 'admin@example.com'\n"
        request = ReviewRequest(
            request_id="req-123",
            artifact_id="art-456",
            artifact_type="source_code",
            content=sensitive_code,
            context={"files": ["mailer.py"]},
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 2. Mock Provider (Ollama)
        mock_provider = AsyncMock()
        mock_provider.reviewer_id = "mock-ollama"
        mock_provider.review.return_value = ReviewVote(
            reviewer_id="mock-ollama",
            decision="approve",
            confidence=0.9,
            rationale="LGTM",
            findings=[]
        )

        # 3. Initialize Council with Real WASM Client (implicitly used by council.py)
        # We need to ensure PIIWasmClient can load. 
        # If WASM fails, the council typically fails open or logs error.
        # We want to verify it SUCCEEDS in redacting.
        
        council = LocalCouncil(providers=[mock_provider])

        # 4. Execute Review
        result = await council.review(request)

        # 5. Verify Mock Provider received REDACTED content
        self.assertTrue(mock_provider.review.called)
        
        # Get the prompt passed to the provider
        args, _ = mock_provider.review.call_args
        prompt_sent = args[0]
        
        # Check that the email was redacted
        self.assertNotIn("admin@example.com", prompt_sent, "PII should not be present in the prompt sent to provider")
        self.assertIn("[HIDDEN", prompt_sent, "Prompt should contain redaction markers")
        
        # Verify the prompt still contains the structure
        self.assertIn("def send_mail():", prompt_sent)

    async def test_council_handles_wasm_failure_gracefully(self):
        """Verify fallback (fail-open) if WASM client crashes."""
        sensitive_code = "pass"
        request = ReviewRequest(
            request_id="req-fail",
            artifact_id="art-fail",
            artifact_type="source_code",
            content=sensitive_code,
        )
        
        mock_provider = AsyncMock()
        mock_provider.reviewer_id = "mock-ollama"
        mock_provider.review.return_value = ReviewVote(
            reviewer_id="mock-ollama",
            decision="abstain",
            confidence=0.0,
            rationale="Abstain",
            findings=[]
        )

        # Patch PIIWasmClient to raise exception
        with patch("guardspine_local_council.council.PIIWasmClient") as MockWasm:
             instance = MockWasm.return_value
             instance.redact.side_effect = RuntimeError("WASM Crash")
             
             council = LocalCouncil(providers=[mock_provider])
             await council.review(request)
             
             # Should still call provider with original prompt (fail-open)
             self.assertTrue(mock_provider.review.called)
             args, _ = mock_provider.review.call_args
             prompt_sent = args[0]
             self.assertIn("pass", prompt_sent)

if __name__ == "__main__":
    unittest.main()
