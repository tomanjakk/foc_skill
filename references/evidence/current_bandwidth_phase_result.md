# 8.5 A 幅相联合复测

本结果替代此前只强调幅值的4.2 kHz整定结果。

用户标准：主要以幅值首次下降到-3 dB判定带宽，在该点相位滞后目标约90°、最大120°。保留共振峰值不超过3 dB、相电流16 A及电压饱和中止。

最终参数：EEPROM相R=0.0954398215 Ω，Ld=Lq=53.9907705 µH；Kp缩放0.70，d/q Kp=0.251956940；串联Ki保持631.323669 s^-1。电流反馈没有额外低通。FOC_CURRENT_BANDWIDTH_IQ_AMPLITUDE_A=8.5，FOC_CURRENT_BANDWIDTH_PHASE_LIMIT_DEG=-120。

| 最终固件复测 | -3 dB带宽Hz | 该点相位° | 峰值增益dB |
| --- | ---: | ---: | ---: |
| A | 1700.764 | -105.012 | 1.024 |
| B | 1708.351 | -105.291 | 1.029 |
| C | 1698.742 | -105.008 | 1.029 |

三次status=2、reason=0，ADC同步错误前后均0，结束均Motor_Disable。数据为current_bw_phase_final_a/b/c.json。试调Kp缩放0.75曾读到2314.9 Hz、-127.1°，相位不合格，未保留。

MKLink确认SWD=10 MHz、profile_confirmed=true；SuperWatch请求间隔设置1 µs。进度仍每0.4 s轮询，未把轮询点当作相位采样。幅相由MCU内部20 kHz同步检波计算；本次没有启动SuperWatch连续波形记录，因此没有宣称实际上位机采样率为1 MHz。

脚本对相位按频率展开，修正+180°/-180°跳变，使用原始Iq幅值找到-3 dB下降穿越，在相邻点插值相位。已用合格-105°和跨越-180°的反例检查判定逻辑。90/120°为闭环跟随相位，不是开环稳定裕度。

Keil编译0错误0警告，pyOCD program/verify/reset/disconnect成功。固件SHA256=2de089c69bf78baa5717b56801d2521ee3bc41def807551cfda4a58b326105c1，任务c105e21e-5dee-4976-bcc3-069b07eccbec。配套AXF/HEX位于work/current_bw_build/STM32g474vet6.axf/.hex，后台已加载该AXF。

未用示波器独立验证模拟电流，也未验证带载高速、d轴独立频响或长时间温升；当前仍为模式2启动扫频的测试固件。
