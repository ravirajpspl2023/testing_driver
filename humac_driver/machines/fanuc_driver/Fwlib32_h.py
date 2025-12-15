# -*- coding: utf-8 -*-
""" Fwlib32_h.py

This file contains ctypes structures to match the data structures
found in the library header Fwlib32.h.

All classes contain `_pack_ = 4`; this comes from Fwlib32.h:
    #pragma pack(push,4)

Don't unit test these because it would basically be running tests against
the ctypes module itself and not any of our own code.

Further documentation can be found in the FOCAS documentation.
Look up the documentation of the Equivalent data type.
For example, for documentation on "AlarmStatus", look up "ODBALM".

"""

import ctypes
class CNC_CONF:
    """Constants"""
    MAX_AXIS = 32
    """int: The maximum number of axes a control will return"""
    ALL_AXES = -1
    """int: A constant value to request that a function return all axes at once"""
    MAX_PATH = 5
    CURRENT_PATH = None
    PROGRAME_NAME = ""
    PROGRAME_ONUMBER = ""
    
CNC = CNC_CONF()

DATAIO_ALARM_MASK = (0x1 << 2) | (0x1 << 7)
SERVO_ALARM_MASK = 0x1 << 6
MACRO_ALARM_MASK = 0x1 << 8
OVERHEAT_ALARM_MASK = 0x1 << 5
OVERTRAVEL_ALARM_MASK = 0x1 << 4
SPINDLE_ALARM_MASK = 0x1 << 9
"""bit masks to determine alarm status
take an alarm data and AND it with the mask
If the result is True the alarm is active
If it's False it's cleared.

For example, see: DriverImplementations.alarmStringBuilder
"""


class AlarmStatus(ctypes.Structure):
    """
    Equivalent of ODBALM
    """
    _pack_ = 4
    _fields_ = [("dummy", ctypes.c_short * 2),
                ("data", ctypes.c_short), ]


ODBALM = AlarmStatus


class LoadElement(ctypes.Structure):
    """
    Equivalent of LOADELM
    """
    _pack_ = 4
    _fields_ = [("data", ctypes.c_long),
                ("decimal", ctypes.c_short),
                ("unit", ctypes.c_short),
                ("name", ctypes.c_char),
                ("suffix1", ctypes.c_char),
                ("suffix2", ctypes.c_char),
                ("reserve", ctypes.c_char), ]

LOADELM = LoadElement


class ServoLoad(ctypes.Structure):
    """
    Equivalent of ODBSVLOAD
    """
    _pack_ = 4
    _fields_ = [("load", LoadElement)]

ODBSVLOAD = ServoLoad


class SpindleLoad(ctypes.Structure):
    """
    Equivalent of ODBSPLOAD
    """
    _pack_ = 4
    _fields_ = [("load", LoadElement),
                ("speed", LoadElement), ]

ODBSPLOAD = SpindleLoad


class StatInfo(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("hdck", ctypes.c_short),
                ("tmmode", ctypes.c_short),
                ("auto", ctypes.c_short),
                ("run", ctypes.c_short),
                ("motion", ctypes.c_short),
                ("mstb", ctypes.c_short),
                ("estop", ctypes.c_short),
                ("alarm", ctypes.c_short),
                ("edit", ctypes.c_short), ]

    @property
    def __dict__(self):
        # unreadable
        return dict((f, getattr(self, f)) for f, _ in self._fields_)


class ModalAux(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("aux_data", ctypes.c_long),
                ("flag1", ctypes.c_char),
                ("flag2", ctypes.c_char), ]


class ModalAuxUnion(ctypes.Union):
    _pack_ = 4
    _fields_ = [("g_data", ctypes.c_char),
                ("g_rdata", ctypes.c_char * 35),
                ("g_1shot", ctypes.c_char * 4),
                ("aux", ModalAux),
                ("raux1", ModalAux * 27),
                ("raux2", ModalAux * CNC.MAX_AXIS), ]
    
class ModalData(ctypes.Structure):
    """
    Equivalent of ODBMDL
    """
    _pack_ = 4
    _fields_ = [("datano", ctypes.c_short),
                ("type", ctypes.c_short),
                ("modal", ModalAuxUnion), ]
    
ODBMDL = ModalData


class ODBEXEPRG(ctypes.Structure):
    """
    Equivalent of ODBEXEPRG
    """
    _pack_ = 4
    _fields_ = [("name", ctypes.c_char * 36),
                ("oNumber", ctypes.c_long), ]
    @property
    def __dict__(self):
        # unreadable
        CNC.PROGRAME_NAME = self.name.decode('utf-8').rstrip('\x00')
        CNC.PROGRAME_ONUMBER = self.oNumber
        return dict((f, getattr(self, f)) for f, _ in self._fields_)
    
class ODBUP (ctypes.Structure):
    _pack_ = 4
    _fields_ = [('dummy', ctypes.c_short *2),
                ('data' , ctypes.c_char * 256)]
    @property
    def __dict__(self):
        return dict((f, getattr(self, f)) for f, _ in self._fields_ if f != "dummy")

class AxisName(ctypes.Structure):
    """
    Equivalent of ODBAXISNAME
    """
    _pack_ = 4
    _fields_ = [("name", ctypes.c_char),
                ("suffix", ctypes.c_char)]


ODBAXISNAME = AxisName


class AxisData(ctypes.Structure):
    """
    Equivalent of ODBAXDT
    """
    _pack_ = 4
    _fields_ = [("axisName", ctypes.c_char * 4),
                ("position", ctypes.c_long),
                ("decimalPosition", ctypes.c_short),
                ("unit", ctypes.c_short),
                ("flag", ctypes.c_short),
                ("_reserved", ctypes.c_short), ]


ODBAXDT = AxisData

class AlarmRecord(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("recordType", ctypes.c_short),
                ("alarmGroup", ctypes.c_short),
                ("alarmNumber", ctypes.c_short),
                ("axis", ctypes.c_byte),
                ("_AlarmRecord_dummy", ctypes.c_byte)]


class MDIRecord(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("recordType", ctypes.c_short),
                ("keycode", ctypes.c_byte),
                ("powerFlag", ctypes.c_byte),
                ("_MDIRecord_dummy", ctypes.c_char * 4), ]


class SignalRecord(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("recordType", ctypes.c_short),
                ("signalName", ctypes.c_byte),
                ("oldSignal", ctypes.c_byte),
                ("newSignal", ctypes.c_byte),
                ("_SignalRecord_dummy", ctypes.c_byte),
                ("signalNumber", ctypes.c_short), ]


class DateOrPower(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("recordType", ctypes.c_short),
                ("year", ctypes.c_byte),
                ("month", ctypes.c_byte),
                ("day", ctypes.c_byte),
                ("powerFlag", ctypes.c_byte),
                ("_DateOrPower_dummy", ctypes.c_byte * 2)]


class OperationHistoryDataUnion(ctypes.Union):
    """
    Union for operation history data
    """
    _pack_ = 4
    _fields_ = [("alarm", AlarmRecord),
                ("mdi", MDIRecord),
                ("signal", SignalRecord),
                ("dateOrPower", DateOrPower), ]


class OperationHistory(ctypes.Structure):
    """
    Equivalent of ODBHIS
    """
    _pack_ = 4
    _fields_ = [("startNumber", ctypes.c_ushort),
                ("_ODBHIS_type", ctypes.c_short),
                ("endNumber", ctypes.c_ushort),
                ("data", OperationHistoryDataUnion * 10)]


ODBHIS = OperationHistory


class ProgramDirectory2(ctypes.Structure):
    """
    Equivalent of PRGDIR2
    """
    _pack_ = 4
    _fields_ = [("number", ctypes.c_short),
                ("length", ctypes.c_long),
                ("comment", ctypes.c_char * 51),
                ("_ProgramDirectory2_dummy", ctypes.c_char), ]

PRGDIR2 = ProgramDirectory2


class PanelSignals150(ctypes.Structure):
    """
    Equivalent of IODBSGNL with less data
    """
    _pack_ = 4
    _fields_ = [("_PanelSignals150_dummy", ctypes.c_short),  # dummy
                ("type", ctypes.c_short),  # data select flag 
                ("mode", ctypes.c_short),  # mode signal 
                ("manualFeedAxis", ctypes.c_short),  # Manual handle feed axis selection signal 
                ("manualFeedDistance", ctypes.c_short),  # Manual handle feed travel distance selection signal 
                ("rapidOverride", ctypes.c_short),  # rapid traverse override signal 
                ("jogOverride", ctypes.c_short),  # manual feedrate override signal 
                ("feedOverride", ctypes.c_short),  # feedrate override signal 
                ("spindleOverride", ctypes.c_short),  # (not used) 
                ("blockDelete", ctypes.c_short),  # optional block skip signal 
                ("singleBlock", ctypes.c_short),  # single block signal 
                ("machineLock", ctypes.c_short),  # machine lock signal 
                ("dryRun", ctypes.c_short),  # dry run signal 
                ("memoryProtection", ctypes.c_short),  # memory protection signal 
                ("feedHold", ctypes.c_short),  # automatic operation halt signal 
                ("manualRapid", ctypes.c_short),  # (not used)
                ("_PanelSignals150_dummy2", ctypes.c_short * 2), ] # dummy


class PanelSignals160(ctypes.Structure):
    """
    Equivalent of IODBSGNL
    """
    _pack_ = 4
    _fields_ = [("_PanelSignals160_dummy", ctypes.c_short),  # dummy 
                ("type", ctypes.c_short),  # data select flag 
                ("mode", ctypes.c_short),  # mode signal 
                ("manualFeedAxis", ctypes.c_short),  # Manual handle feed axis selection signal 
                ("manualFeedDistance", ctypes.c_short),  # Manual handle feed travel distance selection signal 
                ("rapidOverride", ctypes.c_short),  # rapid traverse override signal 
                ("jogOverride", ctypes.c_short),  # manual feedrate override signal 
                ("feedOverride", ctypes.c_short),  # feedrate override signal 
                ("spindleOverride", ctypes.c_short),  # (not used) 
                ("blockDelete", ctypes.c_short),  # optional block skip signal 
                ("singleBlock", ctypes.c_short),  # single block signal 
                ("machineLock", ctypes.c_short),  # machine lock signal 
                ("dryRun", ctypes.c_short),  # dry run signal 
                ("memoryProtection", ctypes.c_short),  # memory protection signal 
                ("feedHold", ctypes.c_short),]  # automatic operation halt signal 

IODBSGNL = PanelSignals160


class PMCData(ctypes.Structure):
    """
    Actual PMC values that were read
    Used to replace anonymous struct in IODBPMC called "u"
    """
    _pack_ = 1
    _fields_ = [("cdata", ctypes.c_byte * 5),
                ("idata", ctypes.c_short * 5),
                ("ldata", ctypes.c_byte * 5), ]

    @property
    def pmcValue(self):
        if self.cdata[0] < 0:
            self.cdata[0] = -self.cdata[0] - 1
        return self.cdata[0]


class PMC(ctypes.Structure):
    """
    A data structure to hold values read from PMC addresses
    Equivalent of IODBPMC
    """
    _pack_ = 4
    _fields_ = [("addressType", ctypes.c_short),
                ("dataType", ctypes.c_short),
                ("startAddress", ctypes.c_short),
                ("endAddress", ctypes.c_short),
                ("data", PMCData), ]

IODBPMC = PMC


class FAxis(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("_absolute", ctypes.c_long * CNC.MAX_AXIS),
                ("_machine", ctypes.c_long * CNC.MAX_AXIS),
                ("_relative", ctypes.c_long * CNC.MAX_AXIS),
                ("_distance", ctypes.c_long * CNC.MAX_AXIS), ]

    @property
    def __dict__(self):
        # unreadable
        return dict((f, [x for x in getattr(self, f)])
                    for (f, _) in self._fields_)
        # return {"absolute": self.absolute,
        #        "machine": self.machine,
        #        "relative": self.relative,
        #        "distance": self.distance}


class OAxis(ctypes.Structure):
    _pack_ = 4
    _fields_ = [("absolute", ctypes.c_long),
                ("machine", ctypes.c_long),
                ("relative", ctypes.c_long),
                ("distance", ctypes.c_long), ]

    @property
    def __dict__(self):
        # unreadable
        return dict((f, getattr(self, f)) for f, _ in self._fields_)


class PositionUnion(ctypes.Union):
    """
    Alias for the anonymous union "pos" defined in some fwlib32 structures
    """
    _pack_ = 4
    _fields_ = [("_faxis", FAxis),
                ("_oaxis", OAxis), ]

    @property
    def __dict__(self):
        # unreadable
        return dict([("faxis", self._faxis.__dict__),
                    ("oaxis", self._oaxis.__dict__)])


class DynamicResult(ctypes.Structure):
    """
    Alias for ODBDY2 because what does that even mean
    """
    _pack_ = 4
    _fields_ = [("_DynamicResult_dummy", ctypes.c_short),
                ("axis", ctypes.c_short),
                ("alarm", ctypes.c_long),
                ("programNumber", ctypes.c_long),
                ("mainProgramNumber", ctypes.c_long),
                ("sequenceNumber", ctypes.c_long),
                ("actualFeed", ctypes.c_long),
                ("actualSpindleSpeed", ctypes.c_long),
                ("position", PositionUnion), ]

    @property
    def __dict__(self):
        # unreadable
        return dict((f, getattr(self, f)) for f, _ in self._fields_)

ODBDY2 = DynamicResult


class IDBPMMGTI(ctypes.Structure):
    """
    Equivalent of IDBPMMGTI in FOCAS documentation
    """
    _pack_ = 4
    _fields_ = [("top", ctypes.c_long),
                ("num", ctypes.c_long), ]


class ODBPMMGET(ctypes.Structure):
    """
    Equivalent of ODBPMMGET in FOCAS documentation
    """
    _pack_ = 4
    _fields_ = [("position", ctypes.c_long),
                ("actualFeed", ctypes.c_long),
                ("data", ctypes.c_long * 20),
                ("number", ctypes.c_long * 20),
                ("axis", ctypes.c_short * 20),
                ("type", ctypes.c_short * 20),
                ("alarmAxis", ctypes.c_char * 40),
                ("alarmNumber", ctypes.c_ushort * 40),
                ("channel", ctypes.c_long),
                ("group", ctypes.c_long), ]


class ProgramData(ctypes.Structure):
    """
    Equivalent of ODBPRO
    """
    _pack_ = 4
    _fields_ = [("dummy", ctypes.c_short * 2),
                ("program", ctypes.c_long),
                ("mainProgram", ctypes.c_long)]


ODBPRO = ProgramData


class ToolGroupInfo(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("group", ctypes.c_short),
        ("dummy", ctypes.c_short),
    ]

class ToolLifeData(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("use_life", ctypes.c_long),
        ("max_life", ctypes.c_long),
        ("life_unit", ctypes.c_short),  # 0: minute, 1: times
        ("dummy", ctypes.c_short),
    ]


class path(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("system",     ctypes.c_short),
        ("group",      ctypes.c_short),
        ("attrib",     ctypes.c_short),
        ("ctrl_axis",  ctypes.c_short),
        ("ctrl_srvo",  ctypes.c_short),
        ("ctrl_spdl",  ctypes.c_short),
        ("mchn_no",    ctypes.c_short),
        ("reserved",   ctypes.c_short)]
    
    @property
    def __dict__(self):
        data = dict((f, getattr(self, f)) for f, _ in self._fields_)
        return data

class ODBSYSEX(ctypes.Structure):
    """
    Reads system information such as distinction of Machining(M) or Turning(T), number of path and number of the controlled axes.
    Use this function to confirm compatibility of CNC's system software and PMC's software or to get the number of controllable axes before reading axis coordinate data such as absolute, machine position.
    """
    _pack_ = 4
    _fields_ =[
        ("max_axis",ctypes.c_short), # maximum controlled axes
        ("max_spdl",ctypes.c_short), # maximum spundle number
        ("max_path",ctypes.c_short), # maximum path number 
        ("max_mchn",ctypes.c_short), # maximum machining group number
        ("ctrl_axis",ctypes.c_short), # controlled axes number 
        ("ctrl_srvo",ctypes.c_short), # servo axis number 
        ("ctrl_spdl",ctypes.c_short), # spindle number     
        ("ctrl_path",ctypes.c_short), # path number  
        ("ctrl_mchn",ctypes.c_short), # number of control machines
        ("reserved",  ctypes.c_short * 3), 
        # Array of path structures
        ("path", path * CNC.MAX_PATH),]
    
    @property
    def __dict__(self):
        data = dict((f, getattr(self, f)) for f, _ in self._fields_ if f != "reserved")
        paths = [self.path[i].__dict__ for i in range(self.ctrl_path)]
        data.update({'path': paths})
        return data
    

class ODBSYS(ctypes.Structure):
    """
    Reads system information such as kind of CNC system, Machining(M) or Turning(T), series and version of CNC system software and number of the controlled axes.
    Use this function to confirm compatibility of CNC's system software and PMC's software or to get the number of controllable axes before reading axis coordinate data such as absolute, machine position.
    """
    _pack_ = 4
    _fields_ = [('addinfo',ctypes.c_short),
                ("max_axis",ctypes.c_short),
                ('cnc_type',ctypes.c_char*2),
                ('mt_type',ctypes.c_char*2),
                ('series',ctypes.c_char*4),
                ('version',ctypes.c_char*4),
                ('axes',ctypes.c_char*2)]
    
    @property
    def __dict__(self):
        data = dict((f, getattr(self, f)) for f, _ in self._fields_)
        CNC.MAX_AXIS = self.max_axis
        return data
    
class ODBST(ctypes.Structure):
    """
    Reads the status information of CNC. The various information is stored in each member of "ODBST".
    """
    _pack_ = 4
    _fields_ =[
                ('dummy',ctypes.c_short*2),
                ('aut',ctypes.c_short),
                ('manual',ctypes.c_short),
                ('run',ctypes.c_short),
                ('edit',ctypes.c_short),
                ('motion',ctypes.c_short),
                ('mstb',ctypes.c_short),
                ('emergency',ctypes.c_short),
                ('write',ctypes.c_short),
                ('labelskip',ctypes.c_short),
                ('alarm',ctypes.c_short),
                ('warning',ctypes.c_short),
                ('battery',ctypes.c_short)]
    # Define mappings for each field's values
    _status_mappings = {
        'aut': {0: "No selection",1: "MDI",2: "TAPE/DNC",3: "MEMory",4: "EDIT",5: "TeacH IN",},
        'manual': {0: "No selection",1: "REFerence",2: "INC·feed",3: "HaNDle",4: "JOG",
                   5: "AnGular Jog",6: "Inc+Handl",7: "Jog+Handl",},
        'run': {0: "STOP",1: "HOLD",2: "STaRT",3: "MSTR",4: "ReSTaRt (not blinking)",5: "PRSR",
                6: "NSRC",7: "ReSTaRt (blinking)",8: "ReSET",13: "HPCC",},
        'edit': {0: "Not editing",1: "EDIT",2: "SeaRCH",3: "VeRiFY",4: "CONDense",5: "READ",6: "PuNCH",},
        'motion': {0: "No motion",1: "MoTioN",2: "DWeLl",3: "Wait",},
        'mstb': { 0: "No MSTB", 1: "FIN", },
        'emergency': { 0: "Not emergency", 1: "EMerGency",},
        'write': { 0: "Not writing", 1: "Writing",},
        'labelskip': {0: "Label SKip", 1: "Not label skip",},
        'alarm': { 0: "No alarm", 1: "ALarM",},
        'warning': { 0: "No warning", 1: "WaRNing",},
        'battery': { 0: "Normal", 1: "BATtery low (memory)", 2: "BATtery low (position detector)",},
    }
    
    @property
    def __dict__(self):
        data = dict((f, self._status_mappings.get(f).get(getattr(self, f))) for f, _ in self._fields_ if f != "dummy")
        return data
    
class ODBST2(ctypes.Structure):
    _pack_ =4
    _fields_=[
        ('hdck',ctypes.c_short),
        ('tmmode',ctypes.c_short),
        ('aut',ctypes.c_short),
        ('run',ctypes.c_short),
        ('motion',ctypes.c_short),
        ('mstb',ctypes.c_short),
        ('emergency',ctypes.c_short),
        ('alarm',ctypes.c_short),
        ('edit',ctypes.c_short),
        ('warning',ctypes.c_short),
        ('o3dchk',ctypes.c_short),
        ('ext_opt',ctypes.c_short),
        ('restart',ctypes.c_short)]
    
    _status_mappings = {
        'hdck': {
            0: "Invalid of manual handle re-trace",
            1: "M.H.RTR.(Manual handle re-trace)",
            2: "NO RVRS.(Backward movement prohibition)",
            3: "NO CHAG.(Direction change prohibition)"},
        'tmmode':{0:"T mode",1:"M mode"},
        'aut':{0:"MDI",1:"MEMory",2:"****",3:"EDIT",4:"HaNDle",5:"JOG",6:"Teach in JOG",
               7:"Teach in HaNDle",8:"INC·feed",9:"REFerence",10:"ReMoTe",},
        'run':{0:'****(reset)',1:'STOP',2:'HOLD',3:'STaRT',4:'MSTR'},
        'motion':{0:'***',1:'MoTioN',2:'DWeLl'},
        'mstb':{0:'***(Others)',1:'FIN'},
        'emergency':{0:"Not emergency",1:"EMerGency",2:"ReSET",3:"WAIT(FS35i only)"},
        'alarm':{0:'***(Others)',1:'ALarM',2:'BATtery low',3:'FAN(NC or Servo amplifier)',4:'PS Warning',
            5:'FSsB warning',6:'LeaKaGe warning',7:'ENCoder warning',8:'PMC alarm'},
        'edit':{           
            0:	'****(Not editing)',
            1:	'EDIT(during editing)',
            2:	'SeaRCH(during searching)',
            3:	'OUTPUT(during output)',
            4:	'INPUT(during input)',
            5:	'COMPARE((during comparing)',
            6:	'Label SKip(label skip status)(30i, 0i-D/F are unused.)',
            7:	'ReSTaRt(during program restart)',
            9:	'PTRR(during tool retraction and recovery mode)',
            10:	'RVRS(during retracing)',
            11:	'RTRY(during reprogressing)',
            12:	'RVED(end of retracing)',
            13:	'HANDLE(during handle overlapping)(30i, 0i-D/F are unused.)',
            14:	'OFfSeT(during tool length measurement mode)',
            15:	'Work OFfSet(during work zero point measurement mode)',
            16:	'AICC(during AI coutour control)(30i, 0i-F)(0i-D:No.13104#0=1)',
            17:	'MEmory-CHecK(checking tape memory)(30i, 0i-D/F are unused.)',
            18:	"CusToMers BoarD(during customers board control)(30i, 0i-D/F are unused.)",
            19:	'SAVE(saving fine torque sensing data)(30i, 0i-D/F are unused.)',
            20:	'AI NANO(during AI nano contour control)(30i, 0i-D/F are unused.)',
            21:	'AI APC(during AI advanced preview control)(0i-D:No.13104#0=1)',
            23:	'AICC 2(during AI coutour control II)(30i, 0i-F)(0i-D:No.13104#0=1)',
            26:	'LEN(change the manual active offset value:length offset change mode)',
            27:	'RAD(change the manual active offset value:radius offset change mode)',
            28:	'WZR(change the manual active offset value:workpiece origin offset change mode)',
            39:	'TCP(during tool center point control of 5-axes machining)',
            40:	'TWP(during tilted working plane command)',
            41:	'TCP+TWP(during tool center point control of 5-axes machining and tilted working plane command)',
            42:	'APC(Advanced Preview Control)(0i-D:No.13104#0=1)',
            43:	'PRG-CHK(High speed program check)',
            44: 'APC(Advanced Preview Control)(0i-D:No.13104#0=0)',
            45: 'S-TCP(during smooth TCP)(30i, 0i-F)',
            46: 'AICC 2(during AI coutour control II)(0i-D:No.13104#0=0)',
            59: 'ALLSAVE(High speed program management:the programs saving in progress)',
            60: 'NOTSAVE(High speed program management:by the programs not saved status)',},
        "warning":{0:'(No warning)',1:'WaRNing(Start from middle of program)'},
        'o3dchk':{
            0	:	'Not 3D interference mode',
            1	:	'3D interference mode by Built-in 3D interference check',
            2	:	'3D interference mode by presonal computer function'},
        'ext_opt':{0:'Normal',2:'Temporary setting mode',3:'Waiting of certification',},
        'restart':{       
            0	:	'It is either of the following status.- Program did not edit.- Parameter No.10330- CNC does not support this function.',
            1	:	'is edited.'}
            }
    
    @property
    def __dict__(self):
        data = dict((f, self._status_mappings.get(f).get(getattr(self, f))) for f, _ in self._fields_ if f != "dummy")
        return data
    
class ODBLOAD(ctypes.Structure):
    _pack_ = 4
    _fields_=[
        ('datano',ctypes.c_short),   # /* Motor type. */
        ('type',ctypes.c_short),     # /* Axis number. */
        ('data',ctypes.c_short* CNC.MAX_AXIS)]  # /* Abnormal load torque data. */   N is the maximum number of controlled axes. 
    
    @property
    def __dict__(self):
        torque = dict((f, getattr(self, f)) for f, _ in self._fields_ if f != "data")
        torque['torque'] = []
        for i in range(CNC.MAX_AXIS):
            torque["torque"].append(self.data[i])
        # if self.data :
        #     for i in self.data:
        #         torque['torque'].append(self.data[i])
        return torque
