import unittest
from mt5.mt5_actions import MT5_actions as mt5_a
import core.global_vars as gv

class MT5_getPeriodTicks_test(unittest.TestCase):
    
    def before_run(self):
        mt5_a.init_MT5()
        mt5_a.authorization(23677, "3C$ap3%H")

    def test_getPeriodTestWithM15(self):
        self.before_run()
        ticks = mt5_a.getPeriodTicks("LKOH", 1764687600, 1764688500 )
        isEmpty = True if len(ticks) > 0 else False
        self.assertTrue(isEmpty)
        print(self.test_getPeriodTestWithM15.__name__)
        print(len(ticks))
        
    def test_getPeriodTestWithH1(self):
        self.before_run()
        ticks = mt5_a.getPeriodTicks("LKOH", 1762380000, 1762383600 )
        isEmpty = True if len(ticks) > 0 else False
        self.assertTrue(isEmpty)
        print(self.test_getPeriodTestWithH1.__name__)
        print(len(ticks))
        
    def test_getPeriodTestWithD1(self):
        self.before_run()
        ticks = mt5_a.getPeriodTicks("LKOH", 1710892800, 1710979200 )
        isEmpty = True if len(ticks) > 0 else False
        self.assertTrue(isEmpty)
        print(self.test_getPeriodTestWithD1.__name__)
        print(len(ticks))

    def test_getPeriodTestWithD1Custom(self):
        self.before_run()
        ticks = mt5_a.getPeriodTicks("LKOH", 1753574400, 1753660800 )
        isEmpty = True if len(ticks) > 0 else False
        self.assertTrue(isEmpty)
        print(self.test_getPeriodTestWithD1Custom.__name__)
        print(len(ticks))
    


if __name__ == '__main__':
    unittest.main(argv=['ignored'], exit=False)

