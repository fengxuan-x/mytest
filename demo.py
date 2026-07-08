from ss_library.shc6xx_mtai import *
from ss_library.shq_logger import *

async def _main_task():
    demo = Ads1220_Driver("COM1")

    await demo.power_up()
    await demo.spi_config()
    await demo.write_reg(0, [0x50])

    rreg = await demo.read_reg(0, 1)
    print_debug(f"读取res = {rreg}")
    await demo.async_close()

asyncio.run(_main_task())
