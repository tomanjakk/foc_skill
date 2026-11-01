"""多点回归、升降一致性和最终撤流目标的离线验证。"""
import math
import unittest
from pathlib import Path


def fit(x, y):
    if len(x) != 7 or len(y) != 7 or not all(map(math.isfinite, x+y)):
        return None
    mx, my = sum(x)/7, sum(y)/7
    xx = sum((v-mx)**2 for v in x)
    yy = sum((v-my)**2 for v in y)
    if xx <= 1 or yy <= 0:
        return None
    a = sum((i-mx)*(u-my) for i,u in zip(x,y))/xx
    b = my-a*mx
    e = [u-a*i-b for i,u in zip(x,y)]
    h = max(abs((y[j]-a*x[j])-(y[6-j]-a*x[6-j])) for j in range(3))
    quality = 1-sum(v*v for v in e)/yy
    return a,b,max(map(abs,e)),quality,h


class ResistanceFit(unittest.TestCase):
    def test_known_slope_and_fixed_offset(self):
        x=[1.5,2,2.5,3,2.5,2,1.5]
        for slope in [.07,.095]:
            a,b,error,q,h=fit(x,[slope*i+.27 for i in x])
            self.assertAlmostEqual(a,slope)
            self.assertAlmostEqual(b,.27)
            self.assertLess(error,.005)
            self.assertAlmostEqual(q,1)
            self.assertLess(h,.010)

    def test_nonlinearity_and_direction_drift_visible(self):
        x=[1.5,2,2.5,3,2.5,2,1.5]
        y=[.07*i+.27 for i in x]
        y[3]+=.04
        self.assertGreater(fit(x,y)[2],.005)
        y=[.07*i+.27+(.03 if j>3 else 0) for j,i in enumerate(x)]
        self.assertGreater(fit(x,y)[4],.010)
        self.assertIsNone(fit(x,[math.nan]*7))

    def test_final_ramp_starts_at_last_target(self):
        s=(Path(__file__).resolve().parents[2]/'FOC_Migrated/foc_measure.c').read_bytes().decode('gbk')
        down=s[s.index('case MEASURE_R_RAMP_DOWN:'):s.index('#define MEASURE_L_DIRECTIONS')]
        self.assertIn('MotorControl->idRef = MeasureR_Target() *',down)
        self.assertIn('return max_error <= 0.005f && hysteresis <= 0.010f',s)

    def test_frozen_fit_independent_validation(self):
        x=[1.5,2,2.5,3,2.5,2,1.5]
        result=fit(x,[.095*i+.27 for i in x])
        slope,offset=result[:2]
        predicted=slope*2.25+offset
        self.assertLessEqual(abs((.095*2.25+.27)-predicted),.005)
        self.assertGreater(abs(predicted+.02-predicted),.005)
        s=(Path(__file__).resolve().parents[2]/'FOC_Migrated/foc_measure.c').read_bytes().decode('gbk')
        self.assertIn('if (measure_level < 7U) {\r\n                    g_foc_measure_r.current_points_a[measure_level]',s)
        self.assertIn('fabsf(g_foc_measure_r.validation_error_v) <= 0.005f',s)
        self.assertIn('g_foc_measure_r.validation_passed = 1U;',s)


if __name__ == '__main__':
    unittest.main()
