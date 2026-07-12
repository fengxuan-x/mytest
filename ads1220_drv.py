import asyncio
from dev_ioboard import DevIOBoardAsync
from dev_ioboard import STM32L433 as LS


class Cmds1220:
    RESET = 0x06
    START = 0x08
    POWERDOWN = 0x2
    RDATA = 0x1F
    RREG = 0x20
    WREG = 0x40
    D_RREG = 0xA0
    D_WREG = 0xC0


class Cmds48B:
    WAKEUP = 0x0
    SLEEP = 0x02
    RESET = 0x06
    SYNC = 0x04
    RDATA = 0x12
    RDATAC = 0x14
    SDATAC = 0x16
    RREG = 0x20
    WREG = 0x40
    SYSOCAL = 0x60
    SYSGCAL = 0x61
    SELFOCAL = 0x62
    D_RREG = 0xA0
    D_WREG = 0xC0


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
        await self.async_open()
        self.attach_ioboard(self.board_id, self.uri)

        await self.ssc_cmd("pav0 0")
        await self.ssc_cmd("dvdd 0")
        for icmd in ["pav0 1", "dvdd 1"]:
            ret = await self.ssc_cmd(icmd)
            await asyncio.sleep(0.1)

        for icmd in ["spix 1 0 0 2 0x50 0x00", "spix 1 0 0 2 0x11 0x90", "spix 1 0 0 2 0x94 0xD0"]:
            await self.dac_cs_low()
            ret = await self.ssc_cmd(icmd)
            await self.dac_cs_high()

        await self.ssc_cmd("avdd 1")
        await self.gpio_init()
        await self.spi_timing()
        await self.reset()
        await asyncio.sleep(0.01)

    # ########################################################################SPI----
    # 设置spi时序，
    async def gpio_init(self):
        # reset config
        await self.gpio_config(group = LS.PC, pin = LS.GPIO_PIN_1, mode = LS.GPIO_MODE_OUTPUT_PP, value = 1, pull = LS.GPIO_NOPULL, alt = 0,
                               speed = LS.GPIO_SPEED_FREQ_HIGH)
        # drdy config
        await self.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_9, mode = LS.GPIO_MODE_INPUT, value = 1, pull = LS.GPIO_NOPULL, alt = 0,
                               speed = LS.GPIO_SPEED_FREQ_HIGH)
        # start config
        await self.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_4, mode = LS.GPIO_MODE_OUTPUT_PP, value = 1, pull = LS.GPIO_NOPULL, alt = 0,
                               speed = LS.GPIO_SPEED_FREQ_HIGH)
        # spi
        await self.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_8, mode = LS.GPIO_MODE_OUTPUT_PP, value = 1, pull = LS.GPIO_NOPULL, alt = 0,
                               speed = 3)  # cs
        await self.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_13, mode = LS.GPIO_MODE_AF_PP, value = 1, pull = LS.GPIO_NOPULL, alt = 5,
                               speed = 3)  # SCK
        await self.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_14, mode = LS.GPIO_MODE_AF_OD, value = 0, pull = LS.GPIO_NOPULL, alt = 5,
                               speed = 3)  # MISO
        await self.gpio_config(group = LS.PB, pin = LS.GPIO_PIN_15, mode = LS.GPIO_MODE_AF_PP, value = 1, pull = LS.GPIO_NOPULL, alt = 5,
                               speed = 3)  # MOSI

    #########################重写#################################
    async def spi_timing(self):
        pass

    async def reset(self):
        pass

    async def get_chip_temp(self):
        pass

    async def sendcmds(self, cmds, rlen=0, ispi=True):
        await self.gpio_write(LS.PB, LS.GPIO_PIN_8, 0)  # cs low
        if ispi:
            val = await self.spi_trans(bus = self.spi_bus, byte_delay = 100, read_count = rlen, cmd_count = len(cmds), tx_bytes = tuple(cmds))
        else:
            val = await self.ssc_cmd(cmds, timeout = 30)
        if rlen and type(val[1]) is not bytes:
            raise Exception("SPI操作发生异常！")
        await self.gpio_write(LS.PB, LS.GPIO_PIN_8, 1)  # cs high
        return val[1]


class Shc6220_Drv(MCU_IO):
    async def spi_timing(self):
        await self.spi_config_ex(bus = self.spi_bus, rx_only = 0, data_8bit = 1, clk_pha_1 = 0, clk_pol_h = 0, clk_div = 16, msb_first = 1)

    async def reset(self):
        await self.sendcmds([Cmds1220.RESET])

    async def read_reg(self, reg, len) -> bytes or int:
        return await self.sendcmds([Cmds1220.RREG | (reg << 2) | (len - 1)] if reg < 4 else [Cmds1220.D_RREG | reg], len)

    async def write_reg(self, reg, val, reg_size=1):
        return await self.sendcmds(
            ([Cmds1220.WREG | (reg << 2) | (reg_size - 1)] if reg < 4 else [Cmds1220.D_WREG | reg]) + list(val.to_bytes(reg_size)), )

    async def read_data_once(self, refv=2.048):
        dlytime = 15
        wait_time = 2000000
        cmd = "spia 1 {} 3 1 0 1 0x200 0 {} {}".format(dlytime, wait_time, Cmds1220.START)
        return self.calvolt(await self.sendcmds(cmd, ispi = False), refv)

    async def continuous_conv(self, read_times: int = 100, refv=2.048):
        val: bytes = await self.read_reg(reg = 0x01, len = 1)
        regval = int.from_bytes(val, byteorder = 'big')
        await self.write_reg(reg = 0x01, val = regval | 0x04)

        delay, wait_time = 1, 2000000
        cmd = f"spir 1 {delay} 3 1 0 1 0x200 0 {wait_time} {read_times} {Cmds1220.START}"
        return await self.calvolt(await self.sendcmds(cmd, ispi = False), refv)

    async def calvolt(self, bcode, refv):
        icode, ivolt = [], []
        for i in range(0, len(bcode), 3):
            icode.append(int.from_bytes(bcode[i:i + 3], signed = True))
            ivolt.append(round(icode[-1] / (1 << 23) * refv, 6))
        return icode, ivolt

    async def get_chip_temp(self):
        # self.write_reg(reg = 0x01, val = 0x02)
        # val = int(sum(self.read_data_once_code(3)) / 3)
        # int_val = (val >> 10) & 0x3FFF
        # if int_val >= 0x2000:
        #     int_val -= 0x4000
        # return int_val * 0.03125
        pass


class Shc6248B_Drv(Shc6220_Drv):
    async def reset(self):
        await self.gpio_write(LS.PB, LS.GPIO_PIN_4, 1)  # SYNC high
        await self.sendcmds([Cmds48B.RESET])

    async def spi_timing(self):
        await self.spi_config_ex(bus = self.spi_bus, rx_only = 0, data_8bit = 1, clk_pha_1 = 0, clk_pol_h = 0, clk_div = 32, msb_first = 1)

    async def read_reg(self, reg, len):
        return await self.sendcmds([Cmds48B.RREG | reg, len - 1] if reg < 0xF else [Cmds48B.D_RREG, reg], len)

    async def write_reg(self, reg, val, reg_size=1):
        return await self.sendcmds(([Cmds48B.WREG | reg, reg_size - 1] if reg < 4 else [Cmds48B.D_WREG, reg]) + list(val.to_bytes(reg_size)), )

    async def read_data_once(self, refv=2.048):
        return await self.calvolt(await self.sendcmds([Cmds48B.RDATA], 3), refv)

    async def continuous_conv(self, read_times: int = 100, refv=2.048):
        delay, wait_time = 1, 2000000
        cmd = f"spir 1 {delay} 3 0 1 1 0x200 0 {wait_time} {read_times} {Cmds48B.RDATA}"
        return await self.calvolt(await self.sendcmds(cmd, ispi = False), refv)

    async def get_chip_temp(self):
        # await self.select_ref_source(vref=Ref_Sel_T.InterRef)
        # await self.set_muxcal(mode=Muxcal_Mode.InterTemp)
        # adc_volt = sum(val_list) / len(val_list) / 8388608 * 2.048 * 1000  # mV
        # temp = (adc_volt - 118) / 0.405 + 25
        # await self.set_muxcal(mode=.Muxcal_Mode.Normal)
        # return round(temp, 1)
        pass


class Shc6258A_Drv(MCU_IO):
    async def reset(self):
        await self.gpio_write(LS.PB, LS.GPIO_PIN_4, 1)  # SYNC high
        await self.gpio_write(LS.PB, LS.GPIO_PIN_8, 0)  # cs low
        cmd = [0xFF] * 32
        for i in range(2):
            await self.spi_trans(bus = self.spi_bus, byte_delay = 1, read_count = 0, cmd_count = 32, tx_bytes = tuple(cmd))
        await self.gpio_write(LS.PB, LS.GPIO_PIN_8, 1)  # cs high

    async def spi_timing(self):
        await self.spi_config_ex(bus = self.spi_bus, rx_only = 0, data_8bit = 1, clk_pha_1 = 0, clk_pol_h = 1, clk_div = 128, msb_first = 1)

    async def read_reg(self, reg, len):
        return await self.sendcmds([0x40 + reg], len)

    async def write_reg(self, reg, val, reg_size=1):
        return await self.sendcmds([reg] + list(val.to_bytes(reg_size)))

    async def read_data_once(self, refv=2.5, isbipolar=True):
        # dlytime = 1
        # wait_time = 2000000
        # cmd = f"spia 0 {dlytime} 3 3 1 1 0x10 0 {wait_time} 0x01 0x01 0x80 0x42"
        # return await self.calvolt(await self.sendcmds(cmd, ispi = False), refv, isbipolar)
        await self.write_reg(1, 0x184, 2)
        return await self.calvolt(await self.read_reg(2, 3), refv, isbipolar)

    async def continuous_conv(self, read_times: int = 100, addr1_val=0x180, refv=2.5, isbipolar=True):
        ch, delay, wait_time = 0, 1, 2000000
        cmd_code = 'spit 1'
        reg_str = "0x{:02x} 0x{:02x}".format((addr1_val >> 8) & 0xFF, addr1_val & 0xFF)
        cmd = f"{cmd_code} {ch} {delay} 3 3 1 1 0x200 0 {wait_time} {read_times} 0x01 {reg_str} 0x42"
        return await self.calvolt(await self.sendcmds(cmd, ispi = False), refv, isbipolar)

    # 私有计算电压
    async def calvolt(self, bcode, refv, isbipolar):
        icode, ivolt = [], []
        for i in range(0, len(bcode), 3):
            icode.append(int.from_bytes(bcode[i:i + 3]))
            if isbipolar:
                ivolt.append(round(((icode[-1] / 2 ** 23) - 1) * refv, 6))
            else:
                ivolt.append((icode[-1] / (2 ** 24) * refv, 6))
        return icode, ivolt


class Shc64115_Drv(Shc6258A_Drv):
    CRC_DISABLED = 0  # Disabled
    CRC_RXOR_WCRC = 1  # XOR checksum enabled for register read transactions. Register writes still CRC with these bits set.
    CRC_RW_CRC = 2  # CRC checksum enabled for read and write transactions.

    async def reset(self):
        self._crc = self.CRC_DISABLED
        await self.gpio_write(LS.PB, LS.GPIO_PIN_4, 1)  # SYNC high
        await self.raw_cmd(f'ssc cmd {self.board_id} 1 1 diop {LS.PB} {LS.GPIO_PIN_7} 5000')  # 5ms plus
        return await self.sendcmds([0xff] * 8)

    async def get_chip_temp(self):
        # volt * 1e5 / 477 - 273.15
        pass

    async def spi_timing(self):
        await self.spi_config_ex(bus = self.spi_bus, rx_only = 0, data_8bit = 1, clk_pha_1 = 1, clk_pol_h = 0, clk_div = 64, msb_first = 1)

    async def read_reg(self, reg, len):
        return await self.sendcmds([0x45, reg] if 0x40 <= reg <= 0x50 else [0x40 | reg], len + 1 if self._crc != self.CRC_DISABLED else len)

    async def write_reg(self, reg, val, reg_size=1):
        cmd = await self.cal_crc(reg, val, ([0x05, reg] if 0x40 <= reg <= 0x50 else [reg]) + list(val.to_bytes(reg_size)))
        return await self.sendcmds(cmd)

    async def cal_crc(self, reg, val, data):
        if self._crc != self.DISABLED or (reg == 0x02 and (val >> 2) & 3):
            if reg == 0x02:
                self._crc = (val >> 2) & 3
            data += [self.crc_calculator.calculate_checksum(data)]
        return data

    async def continuous_conv(self, read_times: int = 100, addr1_val=0x180, refv=2.5, isbipolar=True):
        ch, delay, wait_time = 0, 1, 2000000
        cmd_code = 'spit 1'
        reg_str = "0x{:02x} 0x{:02x}".format((addr1_val >> 8) & 0xFF, addr1_val & 0xFF)
        cmd = f"{cmd_code} {ch} {delay} 3 3 1 1 0x200 0 {wait_time} {read_times} 0x01 {reg_str} 0x42"
        return await self.calvolt(await self.sendcmds(cmd, ispi = False), refv, isbipolar)
