from ss_library.shc6xx_mtai import *
from ss_library.shq_logger import *


async def _main_task():
    demo = Ads1220_Driver("COM8")

    await demo.power_up()
    await demo.spi_config()
    await demo.send_cmds(Commands.RESET)
    await asyncio.sleep(0.1)
    await demo.write_reg(0, [0xd0])

    rreg = await demo.read_reg(0, 1)
    print_debug(f"读取res = {list(rreg)}")

    data = await demo.continuous_conv(read_times = 10)
    print_debug(f"读取cont res_b = {list(data)}")

    vals = []
    for i in range(0, len(data), 3):
        vals.append(int.from_bytes(data[i:i + 3], signed = True))
    print_debug(f"读取cont res_i = {vals}")

    volts = []
    for i in vals:
        volts.append(round(i / (1 << 23) * 2.048, 6))
    print_debug(f"读取cont res_v = {volts}")
    await demo.async_close()


asyncio.run(_main_task())
