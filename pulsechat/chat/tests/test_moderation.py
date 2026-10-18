from django.test import SimpleTestCase, override_settings

from chat.moderation import RateLimiter, moderate


class ModerationTests(SimpleTestCase):
    def test_clean_message_passes_unchanged(self):
        result = moderate("  Hello team!  ")
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "Hello team!")
        self.assertFalse(result.flagged)

    def test_blocked_word_is_masked_and_flagged(self):
        result = moderate("Don't be STUPID about it")
        self.assertTrue(result.ok)
        self.assertEqual(result.text, "Don't be ****** about it")
        self.assertTrue(result.flagged)

    def test_word_boundaries_avoid_false_positives(self):
        self.assertFalse(moderate("dumbbell workout").flagged)

    def test_empty_and_non_text_are_rejected(self):
        self.assertFalse(moderate("   ").ok)
        self.assertFalse(moderate(None).ok)
        self.assertFalse(moderate(42).ok)

    @override_settings(CHAT_MAX_MESSAGE_LENGTH=10)
    def test_too_long_is_rejected(self):
        result = moderate("x" * 11)
        self.assertFalse(result.ok)
        self.assertIn("10", result.error)


class RateLimiterTests(SimpleTestCase):
    def test_blocks_after_limit_then_recovers(self):
        now = [0.0]
        limiter = RateLimiter(max_events=3, window=5, clock=lambda: now[0])
        self.assertTrue(all(limiter.allow() for _ in range(3)))
        self.assertFalse(limiter.allow())
        now[0] = 5.1
        self.assertTrue(limiter.allow())
