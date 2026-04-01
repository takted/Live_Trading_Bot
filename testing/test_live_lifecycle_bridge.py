import unittest

from itrading.src.live_lifecycle_bridge import LiveLifecycleBridge


class _DummyLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))

    def error(self, message, exc_info=False):
        self.messages.append(("error", message))


class LiveLifecycleBridgeTests(unittest.TestCase):
    def test_long_trade_lifecycle_updates_stats(self):
        logger = _DummyLogger()
        bridge = LiveLifecycleBridge(logger=logger, pip_value=0.0001)

        signal = {
            "direction": "LONG",
            "size": 10000,
            "stop_loss": 0.6890,
            "take_profit": 0.6910,
        }
        trade_id = bridge.register_signal("AUDUSD", signal)
        bridge.register_bracket_orders(trade_id, parent_order_id=1001, take_profit_order_id=1002, stop_loss_order_id=1003)

        bridge.on_order_status(order_id=1001, status="Filled", filled=10000, remaining=0, avg_fill_price=0.6900)
        bridge.on_order_status(order_id=1002, status="Filled", filled=10000, remaining=0, avg_fill_price=0.6910)

        snapshot = bridge.get_stats_snapshot()
        self.assertEqual(snapshot["trades"], 1)
        self.assertEqual(snapshot["wins"], 1)
        self.assertEqual(snapshot["losses"], 0)
        self.assertGreater(snapshot["gross_profit"], 0.0)

    def test_short_trade_stop_loss_counts_as_loss(self):
        logger = _DummyLogger()
        bridge = LiveLifecycleBridge(logger=logger, pip_value=0.0001)

        signal = {
            "direction": "SHORT",
            "size": 10000,
            "stop_loss": 0.6910,
            "take_profit": 0.6890,
        }
        trade_id = bridge.register_signal("AUDUSD", signal)
        bridge.register_bracket_orders(trade_id, parent_order_id=2001, take_profit_order_id=2002, stop_loss_order_id=2003)

        bridge.on_execution(order_id=2001, price=0.6900, quantity=10000)
        bridge.on_execution(order_id=2003, price=0.6910, quantity=10000)

        snapshot = bridge.get_stats_snapshot()
        self.assertEqual(snapshot["trades"], 1)
        self.assertEqual(snapshot["wins"], 0)
        self.assertEqual(snapshot["losses"], 1)
        self.assertGreater(snapshot["gross_loss"], 0.0)


if __name__ == "__main__":
    unittest.main()

