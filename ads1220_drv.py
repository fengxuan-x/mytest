import asyncio
import os
from loguru import logger
import sys
import yaml
from dev_ioboard import DevIOBoardAsync
from dev_ioboard import STM32L433 as LS


class Commands:
    RESET = 0x06
    START = 0x08
    POWERDOWN = 0x2
    RDATA = 0x1F
    RREG = 0x20
    WREG = 0x40


class MCU_IO(DevIOBoardAsync):
    def __init__(self, board_id: str = None, uri: str = None, cfg: dict = None):
        self.cfg = cfg
        self.spi_bus = 1
        self.uri = 'ws://127.0.0.1:8189/ssc'
        super(MCU_IO, self).__init__(board_id, self.uri)

    def attach_ioboard1(self, board_id: str = None, uri: str = None):
        uri = self.get_uri(uri)
        self.attach_ioboard(board_id, uri)

    async def dac_cs_low(self):
        await self.ssc_cmd("diow {} {} 0".format(LS.PC, LS.GPIO_PIN_15))

    async def dac_cs_high(self):
        await self.ssc_cmd("diow {} {} 1".format(LS.PC, LS.GPIO_PIN_15))

    async def power_up(self):
        await self.spi_config(bus = self.dac_spi_bus, cpha = self.dac_spi_cpha, cpol = self.dac_spi_cpol,
                              speed_div = self.dac_spi_speed_div)

        await self.ssc_cmd("pav0 0")
        await self.ssc_cmd("dvdd 0")
        for icmd in ["pav0 1", "dvdd 1"]:
            ret = await self.ssc_cmd(icmd)
            await asyncio.sleep(0.1)

        for icmd in ["spix 1 0 0 2 0x50 0x00", "spix 1 0 0 2 0x11 0x90", "spix 1 0 0 2 0x94 0xD0"]:
            await self.dac_cs_low()
            await self.ssc_cmd(icmd)
            await self.dac_cs_high()

        return await self.ssc_cmd("avdd 1")


class Ads1220_Driver(MCU_IO):

    # 设置spi时序，即执行ssc sspi bus 1 0
    async def spi_config(self):
        await self.cs_high()
        await self.ioboard.gpio_config(LS.PB, pin = LS.GPIO_PIN_13, mode = LS.GPIO_MODE_AF_PP, value = 1, pull = LS.GPIO_NOPULL, alt = 5, speed = 3)  # SCK
        await self.ioboard.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_14, mode = LS.GPIO_MODE_AF_OD, value = 0, pull = LS.GPIO_NOPULL, alt = 5, speed = 3)  # MISO
        await self.ioboard.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_15, mode = LS.GPIO_MODE_AF_PP, value = 1, pull = LS.GPIO_NOPULL, alt = 5, speed = 3)  # MOSI
        await self.ioboard.spi_config_ex(bus = self.spi_bus, rx_only = 0, data_8bit = 1, clk_pha_1 = 0, clk_pol_h = 0, clk_div = 16, msb_first = 1)

    async def read_reg(self, reg: int, reg_size: int,  if_cs: bool = True):
        tx_byte = Commands.RREG | (reg << 2) | (reg_size - 1)
        await self.cs_low() if if_cs else ...
        ret, value = await self.ioboard.spi_trans(bus = self.spi_bus, byte_delay = 100, read_count = reg_size, cmd_count = 1,
                                                  tx_bytes = (tx_byte,))
        if type(value) is not bytes:
            raise Exception("读寄存器发生异常！")
        await self.cs_high() if if_cs else ...
        return value

    async def write_reg(self, reg: int, val: int, reg_size: int, if_cs: bool = True):
        write_cmd = Commands.WREG | (reg << 2) | (reg_size - 1)
        tx_bytes = [write_cmd, (val & 0xFF)]
        await self.cs_low() if if_cs else ...
        await self.ioboard.spi_trans(bus = self.spi_bus, byte_delay = 100, read_count = 0, cmd_count = len(tx_bytes),
                                     tx_bytes = tuple(tx_bytes))
        await self.cs_high() if if_cs else ...

    async def send_cmds(self, cmd=Commands.RESET):
        """
        发送xx指令
        """
        await self.cs_low()
        await self.ioboard.spi_trans(bus = self.spi_bus, byte_delay = 1, read_count = 0, cmd_count = 1,tx_bytes = (cmd,))
        await self.cs_high()

    # 单次读
    async def read_data_once(self):
        dlytime = 15
        wait_time = 2000000
        cmd = "spia 1 {} 3 1 0 1 0x200 0 {} {}".format(dlytime, wait_time, Commands.START)
        await self.cs_low()
        _, val = await self.ioboard.ssc_cmd(cmd)
        await self.cs_high()
        if type(val) is bytes:
            return int.from_bytes(val, "big", signed = True)

    async def continuous_conv(self, delay: int = 1, timeout: int = 2000000, read_times: int = 100):
        val = await self.read_reg(reg = 0x01, reg_size = 1)
        regval = int.from_bytes(val, byteorder = 'big')
        await self.write_reg(reg = 0x01, val = regval | 0x04, reg_size = 1)

        cmdx = "spir 1 {} 3 1 0 1 0x200 0 {} {} {}".format(delay, timeout, read_times, Commands.START)
        await self.cs_low()
        ret, values = await self.ioboard.ssc_cmd(cmdx, timeout = 30)
        await self.cs_high()
        return values
