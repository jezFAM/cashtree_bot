import os
import sys
import io
import traceback
import ctypes
import ctypes.wintypes
import socket
import socks
import copy
import json
import re
import configparser
import urllib3
import pickle
import asyncio
import nest_asyncio
import aiofiles
import aioconsole
import ssl
import time
import uuid
import urllib

from asyncio import Lock
from collections import defaultdict
from typing import Optional, Dict, List, Any, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

from telegram import Update
from telegram.ext import ApplicationBuilder, Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import NetworkError

from tqdm import tqdm
from bs4 import BeautifulSoup as bs
from pathlib import Path
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from ast import literal_eval
from urllib.parse import urlparse

from httpx import AsyncClient, Limits, RequestError
from httpx_socks import AsyncProxyTransport
from concurrent.futures import ThreadPoolExecutor

# ★★★★★ 이 부분이 핵심! exe 안에서만 실행되게 ★★★★★
if getattr(sys, 'frozen', False):
    # Playwright가 번들 브라우저 찾는 걸 완전히 차단 → 시스템 Chrome만 사용
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

    # 만약 Chrome 경로가 비표준이라면 보험으로 추가 (필수 아님)
    # possible_chrome_paths = [
    #     r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    #     r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    # ]
    # for path in possible_chrome_paths:
    #     if os.path.exists(path):
    #         os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = path
    #         break

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# 한글깨짐 처리
os.putenv('NLS_LANG', 'KOREAN_KOREA.KO16KSC5601')

# InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 실행윈도우 크기
# os.system("mode con: cols=100 lines=20")


def set_console_size(lines, columns, buffer):
    # STD_OUTPUT_HANDLE의 핸들을 얻어옵니다.
    # -11은 STD_OUTPUT_HANDLE을 의미합니다.
    h_out = ctypes.windll.kernel32.GetStdHandle(-11)

    # 현재 콘솔 창 정보를 가져옵니다.
    csbi = ctypes.create_string_buffer(22)
    res = ctypes.windll.kernel32.GetConsoleScreenBufferInfo(h_out, csbi)
    if res == 0:
        raise OSError("Failed to get console screen buffer info.")

    # 현재 콘솔 창의 크기와 스크롤 버퍼를 변경합니다.
    buf_size = ctypes.wintypes._COORD(columns, buffer)
    ctypes.windll.kernel32.SetConsoleScreenBufferSize(h_out, buf_size)

    window_size = ctypes.wintypes._SMALL_RECT(0, 0, columns - 1, lines - 1)
    ctypes.windll.kernel32.SetConsoleWindowInfo(
        h_out, True, ctypes.byref(window_size))


# 예시: 콘솔 창 크기를 높이 30, 가로 90, 스크롤 버퍼를 80으로 설정
set_console_size(lines=30, columns=90, buffer=80)

# 글로벌 로그 파일 락 생성
log_lock = Lock()
max_log_size = 1024 * 1024  # 10 MB
backup_count = 5


async def writelog(log, telegram=False):
    '''
    비동기 로그 기록 함수
    log : 기록할 log 메세지
    alert_bot : 텔레그램 봇 인스턴스
    telegram : 텔레그램으로 로그를 보낼지 여부
    '''
    global scriptInfo, telegramInfo

    d = datetime.now()
    log_file = Path(scriptInfo.dir_path, f'{scriptInfo.script_name}.log')
    msg = f"{d.strftime('%Y.%m.%d. %H:%M:%S')}\t{log}"

    try:
        if telegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chat_id=telegramInfo.adminChatID, text=f"[{scriptInfo.script_name}] {msg}"))

        # 로그 파일 롤링
        if log_file.exists() and log_file.stat().st_size > max_log_size:
            # 가장 오래된 로그 파일 삭제
            oldest_log = log_file.with_suffix(f'.{backup_count}')
            if oldest_log.exists():
                oldest_log.unlink()
            for i in range(backup_count - 1, 0, -1):
                old_log_file = log_file.with_suffix(f'.{i}')
                if old_log_file.exists():
                    old_log_file.rename(log_file.with_suffix(f'.{i + 1}'))
            log_file.rename(log_file.with_suffix('.1'))

        # 로그 파일에 안전하게 쓰기 위해 락을 사용
        async with log_lock:
            async with aiofiles.open(log_file, 'a', encoding='utf-8') as f:
                await f.write(msg + '\n')
    except Exception as e:
        error_msg = f'{d.strftime("%Y.%m.%d. %H:%M:%S")}\t{traceback.format_exc()}'
        print(error_msg)


# 전역변수


@dataclass(frozen=True)
class ScriptInfo:
    cur_ver: float = field(init=False, default=1.0)
    dir_path: str = field(init=False, default=os.getcwd())
    script_name: str = field(
        init=False, default=os.path.basename(__file__).split(".")[0])


scriptInfo = ScriptInfo()


@dataclass(unsafe_hash=True, order=True)
class ConfigInfo:
    config: configparser.ConfigParser = field(default=None, init=False)

    async def async_init(self):
        global scriptInfo

        ''' 비동기 환경에서 설정 파일을 로드하는 메서드 '''
        config_file = Path(
            f'{scriptInfo.dir_path}\\{scriptInfo.script_name}.ini')
        if config_file.is_file():
            self.config = configparser.ConfigParser()
            async with aiofiles.open(config_file, 'r', encoding='utf-8') as f:
                content = await f.read()
            self.config.read_string(content)
        else:
            msg = f'{scriptInfo.script_name}.ini 파일을 찾을 수 없습니다.\n' \
                f'실행파일과 같은 폴더에 {scriptInfo.script_name}.ini 파일을 복사한 후 다시 실행하세요.'
            asyncio.create_task(writelog(msg, telegram=False))
            raise FileNotFoundError(msg)

    async def change_config_file(self):
        global scriptInfo

        # StringIO를 사용해서 먼저 메모리에 쓰기
        config_string = io.StringIO()
        self.config.write(config_string)
        config_content = config_string.getvalue()
        config_string.close()

        # 파일에 비동기적으로 쓰기
        async with aiofiles.open(Path(f'{scriptInfo.dir_path}\\{scriptInfo.script_name}.ini'), 'w', encoding='utf-8') as configfile:
            await configfile.write(config_content)


@dataclass(unsafe_hash=True, order=True)
class TelegramInfo:
    adminChatID: str = None
    channelChatID: str = None
    chat_token: str = None
    botInfo: Application = field(init=False)

    def initialize_bot(self, proxy_url: str):
        """ApplicationBuilder를 사용하여 botInfo를 초기화하는 메서드"""
        try:
            if not self.chat_token:
                raise ValueError("토큰이 설정되지 않았습니다.")

            # ApplicationBuilder를 통해 Application 인스턴스 생성
            builder = ApplicationBuilder().token(self.chat_token)
            if proxy_url:
                builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

            # Application 객체 빌드
            self.botInfo = builder.build()

        except Exception as e:
            raise ValueError(f"봇 초기화 중 오류 발생: {str(e)}")

# proxy 설정


class ProxyType(Enum):
    """프록시 타입 열거형"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS4A = "socks4a"
    SOCKS5 = "socks5"
    SOCKS5H = "socks5h"


@dataclass(unsafe_hash=True, order=True)
class ProxyInfo:
    _socket = socket.socket
    host: str = None
    port: int = 0
    http_port: int = 0
    url: str = None
    enabled: bool = True
    proxy_type: Optional[ProxyType] = None

    def use_socks(self):
        socket.socket = socks.socksocket

    def unuse_socks(self):
        socket.socket = self._socket


@dataclass(unsafe_hash=True, order=True)
class ImportFileInfo:
    pickleFile: str = None

    async def save_pickle(self, data: dict) -> None:
        '''
        data를 pickle 데이터로 비동기적으로 저장하는 함수
        '''
        async with aiofiles.open(self.pickleFile, 'wb') as f:
            await f.write(pickle.dumps(data))

    async def init_pickle(self) -> None:
        '''
        모든 pickle 데이터를 비동기적으로 삭제하는 함수
        '''
        data = {}
        async with aiofiles.open(self.pickleFile, 'wb') as f:
            await f.write(pickle.dumps(data))

    async def get_all_pickle(self):
        '''
        pickle 데이터를 비동기적으로 불러오는 함수
        '''
        try:
            async with aiofiles.open(self.pickleFile, 'rb') as f:
                data = await f.read()
                return pickle.loads(data)
        except FileNotFoundError:
            msg = f'{self.pickleFile} 파일이 없습니다.'
            asyncio.create_task(writelog(msg, telegram=False))
            return dict()


@dataclass(unsafe_hash=True, order=True)
class DataInfo:
    isAlertMode: bool = False
    diffLen: int = 0
    User_Agent: str = None
    store_nnb: str = None
    store_fwb: str = None
    store_buc: str = None
    store_token: str = None
    maxAnswerBuf: int = 0
    maxAnswerLen: int = 0
    maxAnswerCnt: int = 0
    maxPatternCnt: int = 0
    maxPushCnt: int = 0
    maxPageCnt: int = 0
    maxBackupPageCnt: int = 0
    maxRefreshPageCnt: int = 0
    maxRefresh: int = 0
    maxWorkers: int = 2
    sendInterval: float = 0
    naverInterval: float = 0
    backupInterval: float = 0
    refreshInterval: float = 0
    errInterval: float = 0
    answerFilename: str = None
    buf_refresh_time: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    enable_alertmode_time: List[int] = field(default_factory=list)
    disable_alertmode_time: List[int] = field(default_factory=list)
    enable_notimode_time: List[int] = field(default_factory=list)
    disable_notimode_time: List[int] = field(default_factory=list)
    enable_channel_notimode_time: List[int] = field(default_factory=list)
    disable_channel_notimode_time: List[int] = field(default_factory=list)
    member: List[int] = field(default_factory=list)
    adminMember: List[int] = field(default_factory=list)
    premiumMember: List[int] = field(default_factory=list)
    answerManageMember: List[int] = field(default_factory=list)
    answerKeyword: List[int] = field(default_factory=list)
    answerInfo: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    answerInfo_lock: Lock = field(default_factory=Lock, init=False)
    answerKey: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    answerKey_lock: Lock = field(default_factory=Lock, init=False)
    userInfo: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    userInfo_lock: Lock = field(default_factory=Lock, init=False)
    answerItem: str = None
    exceptLink: List[int] = field(default_factory=list)
    naverBuf: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    naverBuf_lock: Lock = field(default_factory=Lock, init=False)
    refresh_buf_lock: Lock = field(default_factory=Lock, init=False)
    refresh_buf: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    naver_buf_lock: Lock = field(default_factory=Lock, init=False)
    naver_buf: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    refresh_list_lock: Lock = field(default_factory=Lock, init=False)
    refresh_list: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    naverBuf_list: defaultdict[dict] = field(
        default_factory=lambda: defaultdict(dict))
    helpFilename: str = None
    premiumHelpFilename: str = None
    answerManageHelpFilename: str = None
    adminHelpFilename: str = None
    # 사용자별 마지막 알림 시간을 저장하는 필드
    last_alert_time: dict = field(default_factory=dict)
    alert_idle_time: int = 0

    async def json_to_file(self):
        '''
        dict 값을 비동기적으로 JSON 파일로 저장
        '''
        jsonFile = Path(f'{scriptInfo.dir_path}\\{self.answerFilename}')
        async with aiofiles.open(jsonFile, 'w', encoding='utf-8') as file:
            await file.write(json.dumps(self.answerInfo, ensure_ascii=False, indent="\t"))

    async def read_to_json(self):
        '''
        파일에서 JSON 값을 비동기적으로 읽어오는 함수
        '''
        jsonFile = Path(f"{scriptInfo.dir_path}\\{self.answerFilename}")
        async with aiofiles.open(jsonFile, 'r', encoding='utf-8') as file:
            data = await file.read()
            self.answerInfo = json.loads(data)

    def find_duplicate_urls(self):
        '''
        같은 업체인지 확인하는 함수
        '''
        # URL 주소와 해당 URL이 속한 키 값을 저장할 딕셔너리
        result = []
        url_to_keys = {}

        # 입력 데이터를 순회하여 URL 주소 식별 및 저장
        for key, values in self.answerInfo.items():
            for value in values:
                if isinstance(value, list):
                    value = value[0]
                if value.startswith("http"):  # URL 주소인지 확인
                    if value in url_to_keys:
                        url_to_keys[value].append(key)  # 이미 존재하는 URL이면 키 값을 추가
                    else:
                        url_to_keys[value] = [key]  # 새 URL이면 새로운 키 값 리스트로 저장

        # 동일한 URL을 갖는 키 값이 있는지 확인하고 메시지 출력
        for url, keys in url_to_keys.items():
            if len(keys) > 1:  # 동일한 URL을 갖는 키 값이 2개 이상인 경우
                result.append(f"{'와 '.join(keys)} 가 같은 URL을 갖고 있습니다: {url}")

        return result


async def getConfig():
    '''
    스크립트 환경설정 정보를 가져오는 함수
    '''
    global scriptInfo, configInfo
    global dataInfo, answerKeyInfo, naverBufInfo, userInfo
    global proxyInfo

    # 현재 망 선택
    hostname = socket.gethostname()
    await configInfo.async_init()

    # PROXY 정보
    proxy_host_str = configInfo.config.get(
        'proxy', 'proxy_host', fallback='None')
    proxyInfo.host = literal_eval(
        proxy_host_str) if proxy_host_str != 'None' else None  # None 문자열 처리
    proxyInfo.port = int(configInfo.config.get(
        'proxy', 'proxy_port', fallback=0))
    proxyInfo.http_port = int(configInfo.config.get(
        'proxy', 'proxy_port_http', fallback=0))
    if proxyInfo.host and proxyInfo.port != 0:
        proxyInfo.proxy_url = f'socks5://{proxyInfo.host}:{proxyInfo.port}'
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5,
                              proxyInfo.host, proxyInfo.port)
    elif proxyInfo.host and proxyInfo.http_port != 0:
        proxyInfo.proxy_url = f'http://{proxyInfo.host}:{proxyInfo.http_port}'
    else:
        proxyInfo.proxy_url = None

    # Telegram 정보
    telegramInfo.adminChatID = literal_eval(
        configInfo.config['telegram']['admin_chat_id'])
    telegramInfo.channelChatID = literal_eval(
        configInfo.config['telegram']['channel_id'])
    telegramInfo.chat_token = literal_eval(
        configInfo.config['telegram']['chat_token'])

    # FILE 정보
    answerKeyInfo.pickleFile = literal_eval(
        configInfo.config['FILE']['answerKey_file'])
    naverBufInfo.pickleFile = literal_eval(
        configInfo.config['FILE']['naverBuf_file'])
    userInfo.pickleFile = literal_eval(
        configInfo.config['FILE']['userInfo_file'])
    dataInfo.helpFilename = literal_eval(
        configInfo.config['FILE']['help_file'])
    dataInfo.premiumHelpFilename = literal_eval(
        configInfo.config['FILE']['premium_help_file'])
    dataInfo.answerManageHelpFilename = literal_eval(
        configInfo.config['FILE']['answer_manage_help_file'])
    dataInfo.adminHelpFilename = literal_eval(
        configInfo.config['FILE']['admin_help_file'])

    # DATA 정보
    dataInfo.answerFilename = literal_eval(
        configInfo.config['DATA']['answerFilename'])
    await dataInfo.read_to_json()
    dataInfo.diffLen = int(configInfo.config['DATA']['diff_length'])
    dataInfo.User_Agent = literal_eval(configInfo.config['DATA']['User_Agent'])
    dataInfo.store_nnb = literal_eval(configInfo.config['DATA']['store_nnb'])
    dataInfo.store_fwb = literal_eval(configInfo.config['DATA']['store_fwb'])
    dataInfo.store_buc = literal_eval(configInfo.config['DATA']['store_buc'])
    dataInfo.store_token = literal_eval(
        configInfo.config['DATA']['store_token'])
    dataInfo.maxAnswerBuf = int(configInfo.config['DATA']['max_answer_buf'])
    dataInfo.maxAnswerLen = int(configInfo.config['DATA']['max_answer_len'])
    dataInfo.maxAnswerCnt = int(configInfo.config['DATA']['max_answer_cnt'])
    dataInfo.maxPatternCnt = int(configInfo.config['DATA']['max_pattern_cnt'])
    dataInfo.maxPushCnt = int(configInfo.config['DATA']['max_push_cnt'])
    dataInfo.alert_idle_time = int(
        configInfo.config['DATA']['alert_idle_time'])
    dataInfo.maxPageCnt = int(configInfo.config['DATA']['max_pages'])
    dataInfo.maxBackupPageCnt = int(configInfo.config['DATA']['backup_pages'])
    dataInfo.maxRefreshPageCnt = int(
        configInfo.config['DATA']['refresh_pages'])
    dataInfo.maxRefresh = int(configInfo.config['DATA']['max_refresh'])
    dataInfo.maxWorkers = int(configInfo.config['DATA']['max_workers'])
    dataInfo.sendInterval = float(configInfo.config['DATA']['interval'])
    dataInfo.naverInterval = float(configInfo.config['DATA']['naver_interval'])
    dataInfo.backupInterval = float(
        configInfo.config['DATA']['backup_interval'])
    dataInfo.refreshInterval = float(
        configInfo.config['DATA']['refresh_interval'])
    dataInfo.errInterval = float(configInfo.config['DATA']['err_interval'])
    dataInfo.buf_refresh_time = literal_eval(
        configInfo.config['DATA']['buf_refresh_time'])
    dataInfo.enable_alertmode_time = literal_eval(
        configInfo.config['DATA']['enable_alert_mode_time'])
    dataInfo.disable_alertmode_time = literal_eval(
        configInfo.config['DATA']['disable_alert_mode_time'])
    dataInfo.enable_notimode_time = literal_eval(
        configInfo.config['DATA']['enable_noti_mode_time'])
    dataInfo.disable_notimode_time = literal_eval(
        configInfo.config['DATA']['disable_noti_mode_time'])
    dataInfo.enable_channel_notimode_time = literal_eval(
        configInfo.config['DATA']['enable_channel_noti_mode_time'])
    dataInfo.disable_channel_notimode_time = literal_eval(
        configInfo.config['DATA']['disable_channel_noti_mode_time'])
    dataInfo.exceptLink = literal_eval(
        configInfo.config['DATA']['except_link'])
    dataInfo.adminMember = literal_eval(
        configInfo.config['DATA']['admin_member'])
    dataInfo.premiumMember = literal_eval(
        configInfo.config['DATA']['premium_member'])
    dataInfo.member = dataInfo.premiumMember + \
        literal_eval(configInfo.config['DATA']['member'])
    dataInfo.answerManageMember = literal_eval(
        configInfo.config['DATA']['answer_manage_member'])
    dataInfo.answerKeyword = literal_eval(
        configInfo.config['DATA']['answer_keyword'])


def convertToInitialLetters(text):
    '''
    한글에서 독립적인 초성 자모를 가져오는 함수
    알파벳, 숫자, '-'는 그대로 유지
    복합 자음은 각 자음으로 분할
    '''
    # 초성 리스트 (유니코드 자모 코드)
    CHOSUNG = [
        'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
    ]
    JAMO_START_LETTER = 44032
    JAMO_END_LETTER = 55203
    JAMO_CYCLE = 588

    # 복합 자음 매핑 (각 복합 자음을 분해할 단일 자음 리스트)
    COMPLEX_CONSONANTS = {
        'ㄳ': 'ㄱㅅ',
        'ㄵ': 'ㄴㅈ',
        'ㄶ': 'ㄴㅎ',
        'ㄺ': 'ㄹㄱ',
        'ㄻ': 'ㄹㅁ',
        'ㄼ': 'ㄹㅂ',
        'ㄽ': 'ㄹㅅ',
        'ㄾ': 'ㄹㅌ',
        'ㄿ': 'ㄹㅍ',
        'ㅀ': 'ㄹㅎ',
        'ㅄ': 'ㅂㅅ'
    }

    # 완성형 한글인지 확인
    def isCompleteHangul(ch):
        return JAMO_START_LETTER <= ord(ch) <= JAMO_END_LETTER

    result = ""
    for ch in text:
        if isCompleteHangul(ch):  # 완성형 한글 글자인 경우 초성 추출
            cho_index = (ord(ch) - JAMO_START_LETTER) // JAMO_CYCLE
            result += CHOSUNG[cho_index]
        elif ch in COMPLEX_CONSONANTS:  # 복합 자음인 경우 분해
            result += COMPLEX_CONSONANTS[ch]
        # 알파벳, 숫자, '-', '@', '*' 단일 자음은 그대로 유지
        elif ch.isalpha() or ch.isdigit() or ch == '-' or ch == '*' or ch == '@' or ch in CHOSUNG:
            result += ch

    return result


def find_partial_key(data, partial_key):
    """
    JSON 데이터에서 주어진 부분 문자열이 키와 일치하는 경우 해당 키를 반환합니다.
    :param data: JSON 데이터
    :param partial_key: 찾고자 하는 부분 문자열
    :return: 부분 문자열과 일치하는 키 또는 None
    """
    if not partial_key:
        return None

    partial_words = partial_key.split("-")

    for key in data:
        key_words = key.split("-")

        if all(word in key_words for word in partial_words):
            return key

    return None


def manage_items(items_list, new_item, maxCnt):
    '''
    리스트으 아이템 갯수를 제한하면서 아이템을 입력하는 함수
    items_list  : 기존 정답 리스트
    new_item : 추가할 정답
    maxCnt : 리스트 최대 갯수
    '''
    global dataInfo

    # 'http'을 포함한 아이템은 제외하고 나머지 아이템의 수를 확인
    non_http_items = [item for item in items_list if not isinstance(
        item, list) and not "http" in item]

    # 'http'를 포함하지 않는 아이템의 수가 최대 보관 갯수 이상이면, 앞에서부터 아이템을 삭제
    while len(non_http_items) > maxCnt - 1:
        for i in range(len(items_list)):
            if not isinstance(items_list[i], list) and not "http" in items_list[i]:
                del items_list[i]
                break  # 한 아이템을 삭제한 후 다시 non_http_items 리스트를 업데이트
        non_http_items = [item for item in items_list if not isinstance(
            item, list) and not "http" in item]

    # 새 아이템을 링크가 아닌 경우 마지막에 추가, 아니면 첫 번째 위치에 추가
    if ("http" not in new_item or contains_any_except_link(new_item, dataInfo.exceptLink)):
        items_list.append(new_item)
    else:
        items_list.insert(0, new_item)

    return items_list


def replace_content_with_user_settings(
    content: str,
    replacements: dict
) -> str:
    """
    주어진 content의 placeholder들을 사용자 설정 값으로 대체합니다.

    Args:
        content (str): 대체할 placeholder가 포함된 원본 문자열
        replacements (dict): 대체할 값을 갖는 dict 데이터

    Returns:
        str: placeholder가 사용자 설정 값으로 대체된 문자열

    Example:
        >>> content = "noti: {noti}, alert: {alert}, channel_noti: {channel_noti}"
        >>> result = replace_content_with_user_settings(content, "user123", data_info)
    """

    result = content
    for key, value in replacements.items():
        result = result.replace(key, str(value))

    return result


async def add_answerInfo(keyword, answer, chatID, isTelegram):
    '''
    정답을 추가하는 함수
    keyword : 정답을 추가할 키워드
    answer : 추가할 정답
    chatID : 결과를 알려줄 user id
    isTelegram : telegram 알림여부
    '''
    global dataInfo, telegramInfo

    isUpdate = False
    isNew = False
    isRemove = False
    sameAsBefore = False

    # 정답제목이 없으면 리턴
    if not bool(keyword):
        return False

    if answer.startswith('-'):
        answer = answer[1:]
        isRemove = True
    # 공백제거
    answer = answer.strip()

    # 정답을 입력할 제목 선택
    if keyword in dataInfo.answerInfo:
        key = keyword
    else:
        key = find_partial_key(dataInfo.answerInfo, keyword)

    if bool(key):
        if answer in dataInfo.answerInfo[key]:
            if isRemove:
                async with dataInfo.answerInfo_lock:
                    # - 기호로 시작하면 기존 정답에서 제거
                    dataInfo.answerInfo[key].remove(answer)
                isUpdate = True
            elif ("http" in answer and not contains_any_except_link(answer, dataInfo.exceptLink)):
                # answer가 리스트의 링크와 같으면 아무것도 안함
                pass
            elif dataInfo.answerInfo[key][-1] != answer:
                # answer가 리스트의 마지막 아이템이 아닌 경우에만 업데이트
                async with dataInfo.answerInfo_lock:
                    dataInfo.answerInfo[key].remove(answer)
                    dataInfo.answerInfo[key].append(answer)
                isUpdate = True
        else:
            if not isRemove:
                # answer가 리스트에 존재하지 않으면 새로 추가
                async with dataInfo.answerInfo_lock:
                    dataInfo.answerInfo[key] = manage_items(
                        dataInfo.answerInfo[key], answer, dataInfo.maxAnswerBuf)
                isUpdate = True
                isNew = True
            else:
                # answer가 리스트에 존재하지 않으면 제거할 답이 없으므로 아무것도 안함
                pass
    else:
        if not isRemove:
            # 키워드에 해당하는 데이터가 없는 경우 새로운 리스트를 만들고 answer 추가
            async with dataInfo.answerInfo_lock:
                dataInfo.answerInfo[keyword] = [answer]
            dupList = dataInfo.find_duplicate_urls()
            if bool(dupList):
                if isTelegram:
                    asyncio.gather(
                        *[telegramInfo.botInfo.bot.send_message(chatID, dup, disable_notification=True) for dup in dupList])
                else:
                    list(map(lambda dup: print(dup), dupList))
                async with dataInfo.answerInfo_lock:
                    del dataInfo.answerInfo[keyword]
            else:
                isUpdate = True
                isNew = True
        else:
            # key가 리스트에 존재하지 않으면 제거할 문제가 없으므로 아무것도 안함
            pass

    # 기출문제 정보를 업데이트
    if isUpdate:
        await dataInfo.json_to_file()

    # 새로운 답이면 출력
    if isNew:
        msg = f'{key if bool(key) else keyword} 답 : "{answer}" 추가 💾'
    elif isRemove:
        if isUpdate:
            msg = f'{key if bool(key) else keyword} 답 : "{answer}" 제거 💣'
        else:
            msg = f'{key if bool(key) else keyword} 답: "{answer}" 은 이미 제거 되었어요 🤔'
    elif isUpdate:
        msg = f'{key if bool(key) else keyword} 답 : "{answer}" 은 이미 있습니다. 😉'
    else:
        msg = f'{key if bool(key) else keyword} 답: "{answer}" 을 업데이트 하지 않았습니다. 😨'
        sameAsBefore = True

    # 정답추가 결과 알림
    if isTelegram:
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))
    print(msg)

    return sameAsBefore


async def handle_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    채널 대화망 메세지처리 함수
    update : update 객체
    context : context 객체
    '''
    global dataInfo, telegramInfo, userInfo

    try:
        if update.channel_post:
            userID = str(
                update.channel_post.from_user.id) if update.channel_post.from_user else None
            message_str = update.channel_post.text
        elif update.edited_channel_post:
            userID = str(
                update.edited_channel_post.from_user.id) if update.edited_channel_post.from_user else None
            message_str = update.edited_channel_post.text
        else:
            return
        message_edit = message_str.replace(" ", "").lower()

        if not bool(message_edit):
            # 입력한 메세지가 없으면 리턴
            return
        # 관리자가 쓴 글이 아니거나 구경미션이거나 ";" 으로 시작하면 기출문제 아님

        if userID != telegramInfo.adminChatID or '구경미션' in message_edit or message_edit.startswith(";"):
            return
        elif message_str[-1] == '답':
            # 메시지 마지막 글자가 "답" 이면 기출문제 제목
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_title'] = message_edit.replace("답", "")
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            # msg = f'정답제목 : {dataInfo.answerKey.get(f"{userID}_title", "없음")}'
            # await telegramInfo.botInfo.bot.send_message(telegramInfo.channelChatID, msg, disable_notification=True)
            return
        elif bool(dataInfo.answerKey[f'{userID}_title']):
            # 문제 제목이 있고 "답" 이라는 글자가 없으면 기출문제 답
            sameAsBefore = await add_answerInfo(
                dataInfo.answerKey[f'{userID}_title'], message_str, userID, True)
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_title'] = None
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            # 기출문제 중복체크
            dupList = dataInfo.find_duplicate_urls()
            asyncio.gather(
                *[telegramInfo.botInfo.bot.send_message(telegramInfo.adminChatID, dup) for dup in dupList])
            # for dup in dupList:
            #     await telegramInfo.botInfo.bot.send_message(telegramInfo.adminChatID, dup)
            #     # await asyncio.sleep(dataInfo.sendInterval)
            return
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))


async def update_answerInfo():
    '''
    두개의 dict 데이터를 비교하는 함수
    '''
    global dataInfo

    # 기존 answerInfo 정보
    async with dataInfo.answerInfo_lock:
        original_data = copy.deepcopy(dataInfo.answerInfo)
        # answerInfo 업데이트
        await dataInfo.read_to_json()
        updated_data = dataInfo.answerInfo

    # 변경사항과 삭제사항을 담을 딕셔너리
    changes = {}
    deletions = {}

    # 업데이트된 데이터에서 각 항목을 검사하여 변경사항 확인
    for key, value in updated_data.items():
        if key not in original_data:
            changes[key] = value
        else:
            changed_values = [
                item for item in value if item not in original_data[key]]
            if changed_values:
                changes[key] = changed_values

    # 원본 데이터에서 각 항목을 검사하여 삭제사항 확인
    for key, value in original_data.items():
        if key not in updated_data:
            deletions[key] = value
        else:
            removed_values = [
                item for item in value if item not in updated_data[key]]
            if removed_values:
                deletions[key] = removed_values

    return changes, deletions


def format_time(seconds):
    '''
    tqdm 의 남은시간 정보를 포맷팅하는 함수
    '''
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:  # 1시간 이상일 경우
        return f"{hours:02d}시간 {minutes:02d}분 {seconds:02d}초"
    else:      # 1시간 미만일 경우
        return f"{minutes:02d}분 {seconds:02d}초"


def dict_values_to_string(dict_data):
    '''딕셔너리의 값들을 문자열로 변환하고 ", "로 연결하는 함수'''
    return ", ".join(str(value) for value in dict_data.values())


def find_keys_with_non_url_first_item(data_dict):
    '''
    정답의 첫번째 item 이 url 인지 확인하
    '''
    # 결과를 저장할 리스트 초기화
    non_url_keys = []

    # 딕셔너리의 각 키와 값을 순회
    for key, value in data_dict.items():
        # 첫 번째 아이템이 URL이 아닌지 확인
        if isinstance(value[0], list):
            if 'http' not in value[0][0]:
                # URL이 아니면 결과 리스트에 키 추가
                non_url_keys.append(key)
        else:
            if 'http' not in value[0]:
                # URL이 아니면 결과 리스트에 키 추가
                non_url_keys.append(key)

    # 결과 리스트 반환
    return non_url_keys


def find_keys_with_short_list(data_dict):
    '''
    스토어에 상품 및 상호 id 정보가 없는 링크 확인
    '''
    # 결과를 저장할 리스트 초기화
    keys_with_short_list = []

    # data_dict의 각 키(key)에 대해 반복
    for key, value in data_dict.items():
        # 첫 번째 값이 리스트이고 그 길이가 2 이하인지 확인
        if isinstance(value[0], list):
            if len(value[0]) < 2:
                keys_with_short_list.append(key)
            elif len(value[0]) < 3 and 'place' not in value[0][0]:
                keys_with_short_list.append(key)

    # 조건을 만족하는 키들의 리스트 반환
    return keys_with_short_list


def contains_any_except_link(value, checkList):
    '''
    주어진 문자열 value에서 checkList 리스트 안의 어떤 문자열이라도 포함되어 있는지 확인하는 함수

    Parameters:
    value (str): 확인할 문자열
    checkList (list): 포함 여부를 확인할 문자열 목록

    Returns:
    bool: exceptLink의 어떤 문자열도 value에 포함되어 있으면 True, 그렇지 않으면 False
    '''
    return any(link in value for link in checkList)


async def change_key(old_key, new_key):
    '''
    key 를 변경하는 함수
    '''
    global dataInfo

    result = False

    if old_key in dataInfo.answerInfo:
        async with dataInfo.answerInfo_lock:
            dataInfo.answerInfo[new_key] = dataInfo.answerInfo.pop(old_key)
            await dataInfo.json_to_file()
        print(f'{old_key} → {new_key}')
        # 기출문제 정보를 업데이트
        result = True

    return result


def is_integer(input_value):
    try:
        # 입력값을 정수로 변환 시도
        int(input_value)
        return True
    except ValueError:
        # 변환에 실패하면 ValueError 발생
        return False


def check_member(userID):
    '''
    멤버인지 확인하는 함수
    userID : 멤버인지 확인할 ID
    '''
    global dataInfo

    return True if userID in dataInfo.member else False


def extract_dynamic_number_from_url(url):
    '''
    URL에서 유동적인 문자열 뒤의 숫자를 추출하는 함수
    '''
    pattern = r'(\w+)/(\d+)'
    match = re.search(pattern, url)
    return match.group(2) if match else None


def remove_digits(message_str):
    # message_str의 각 문자를 순회하며 숫자가 아닌 것만 필터링
    result = ''.join(ch for ch in message_str if not ch.isdigit())
    return result


def extract_values(data, keys, isFirst=True, isMerge=False):
    '''
    dict 데이터에서 원하는 키의 데이터만 추출하는 함수
    '''
    results = []

    # 데이터가 딕셔너리인 경우 각 키-값 쌍을 확인
    if isinstance(data, dict):
        dict_results = []
        for key, value in data.items():
            if not bool(value):
                # value 가 없으면 pass
                continue
            # 관심 있는 키의 값이면 결과에 추가
            if key in keys:
                if key == 'createDate':
                    results.append({key: (datetime.fromisoformat(
                        value) + timedelta(hours=9)).strftime('%y.%m.%d.')})
                else:
                    results.append({key: value.replace('\n', ' ')})
            # 값이 딕셔너리이거나 리스트이면 재귀적으로 탐색
            elif isinstance(value, list) or isinstance(value, dict):
                results.extend(extract_values(
                    value, keys, isFirst=False, isMerge=isMerge))
    # 데이터가 리스트인 경우 각 요소에 대해 재귀적으로 탐색
    elif isinstance(data, list):
        for item in data:
            dict_results = extract_values(
                item, keys, isFirst=False, isMerge=isMerge)
            if dict_results:
                if not isMerge:
                    dict_list = []
                    for key in keys:
                        for dict_value in dict_results:
                            if key in dict_value:
                                dict_list.append(dict_value[key])
                    results.append('\n'.join(dict_list))
                else:
                    for dict_list in dict_results:
                        results.append(dict_list)

    if isFirst:
        dict_list = []
        for item in results:
            if isinstance(item, dict):
                dict_list.append(item)
        if dict_list:
            dict_result = []
            for key in keys:
                dict_item = []
                for dict_data in dict_list:
                    if key in dict_data:
                        dict_item.append(dict_data[key])
                        results.remove(dict_data)
                dict_result.append(', '.join(dict_item))
            results.append('\n'.join(dict_result))
    return results


def split_strings(input_str):
    '''
    입력한 문자열을 자음과 완성된 글자로 분리하는 함수
    '''
    # 입력 문자열을 분리
    if ',' in input_str:
        parts = input_str.split(',')
    else:
        parts = input_str.split(' ')

    # 결과를 담을 리스트 초기화
    result = []

    # 각 문자열을 검사하여 임시 리스트에 분리
    for part in parts:
        part = part.strip()  # 공백 제거

        # 자음만 있는 문자열과 아닌 문자열 분리
        split_parts = re.findall(r'[ㄱ-ㅎ]+|[^ㄱ-ㅎ]+', part)

        # 분리된 부분을 결과 리스트에 추가
        result.extend(split_parts)

    # 중복 제거 및 순서 유지
    seen = set()
    unique_result = []
    for item in result:
        if item not in seen:
            unique_result.append(item)
            seen.add(item)

    return unique_result


def extract_strings_before_keyword(input_string, keyword, direction):
    '''
    input_string 에서 keyword 를 앞 또는 뒤 문자열을 검색하는 함수
    direction : left of right
    '''

    result = []

    # keywoard 가 포함된 위치 확인
    for match in re.finditer(keyword, input_string, re.IGNORECASE):
        if direction == 'left':
            start_index = match.start()
            matched_text = input_string[:start_index].strip()
        elif direction == 'right':
            start_index = match.end()
            matched_text = input_string[start_index:].strip()
        if matched_text:
            result.append(matched_text.replace('…', '...'))
    return result


class CookieManager:
    """웹사이트 별 쿠키를 관리하는 클래스"""

    def __init__(self):
        self.domain_cookies = {}  # 도메인별 쿠키 저장소

    def extract_domain(self, url):
        """URL에서 기본 도메인을 추출합니다"""
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc
        # 서브도메인 제거 (예: m.blog.naver.com -> naver.com)
        parts = domain.split('.')
        if len(parts) > 2:
            return '.'.join(parts[-2:])
        return domain

    def get_cookies_for_url(self, url):
        """특정 URL에 적용할 쿠키를 가져옵니다"""
        domain = self.extract_domain(url)
        return self.domain_cookies.get(domain, {})

    def update_from_response(self, response, request_url):
        """응답에서 Set-Cookie 헤더를 처리하여 쿠키 저장소를 업데이트합니다"""
        domain = self.extract_domain(request_url)

        # 도메인에 대한 쿠키 딕셔너리가 없으면 생성
        if domain not in self.domain_cookies:
            self.domain_cookies[domain] = {}

        # 응답 헤더에서 쿠키 추출
        cookies = response.cookies
        for name, value in cookies.items():
            self.domain_cookies[domain][name] = value

    def get_cookie_header(self, url):
        """특정 URL에 대한 쿠키 헤더 문자열을 반환합니다"""
        cookies = self.get_cookies_for_url(url)
        if not cookies:
            return ""
        return "; ".join([f"{name}={value}" for name, value in cookies.items()])

    def set_cookies_from_playwright(self, playwright_cookies: List[Dict], base_url: str):
        """Playwright에서 가져온 쿠키를 저장소에 추가합니다"""
        domain = self.extract_domain(base_url)

        if domain not in self.domain_cookies:
            self.domain_cookies[domain] = {}

        # Playwright 쿠키 형식: {'name': '...', 'value': '...', 'domain': '...', ...}
        for cookie in playwright_cookies:
            if 'name' in cookie and 'value' in cookie:
                self.domain_cookies[domain][cookie['name']] = cookie['value']

    def get_cookies_for_playwright(self, url: str) -> List[Dict]:
        """저장된 쿠키를 Playwright 형식으로 변환하여 반환합니다

        Args:
            url: 쿠키를 가져올 URL

        Returns:
            Playwright 형식의 쿠키 리스트
            예: [{'name': 'NNB', 'value': 'xxx', 'domain': '.naver.com', 'path': '/'}, ...]
        """
        domain = self.extract_domain(url)
        cookies = self.get_cookies_for_url(url)

        if not cookies:
            return []

        playwright_cookies = []
        for name, value in cookies.items():
            playwright_cookies.append({
                'name': name,
                'value': value,
                'domain': f'.{domain}',  # .naver.com 형식 (서브도메인에서도 사용 가능)
                'path': '/',
                'httpOnly': False,
                'secure': True,
                'sameSite': 'Lax'
            })

        return playwright_cookies


class BrowserLikeClient:
    """실제 브라우저와 유사하게 동작하는 HTTP 클라이언트"""

    def __init__(self, user_agent, store_token, store_nnb: Optional[str] = None, store_fwb: Optional[str] = None, store_buc: Optional[str] = None, use_playwright_cookies: bool = False, proxy_config: Optional[Union[str, ProxyInfo]] = None, **kwargs):
        """
        Args:
            user_agent: 사용할 User-Agent 문자열
            store_token: 네이버 스토어 보안 토큰
            store_nnb: 네이버 NNB 쿠키 (선택 사항, Playwright 없이 요청 시 필요)
            store_fwb: 네이버 FWB 쿠키 (선택 사항, Playwright 없이 요청 시 필요)
            store_buc: 네이버 BUC 쿠키 (선택 사항, Playwright 없이 요청 시 필요)
            use_playwright_cookies: Playwright에서 가져온 쿠키를 사용하는지 여부 (ini 쿠키 중복 방지)
            proxy_config: 프록시 설정 (선택 사항)
        """
        self.cookie_manager = CookieManager()
        self.user_agent = user_agent
        self.config = self._parse_proxy_config(proxy_config)
        self.store_nnb = store_nnb
        self.store_fwb = store_fwb
        self.store_buc = store_buc
        self.store_token = store_token
        self.use_playwright_cookies = use_playwright_cookies
        self.client_kwargs = kwargs
        self.client = None
        self._validate_and_detect_proxy_type()
        self._initialize_client()

    def _parse_proxy_config(self, proxy_config: Optional[Union[str, ProxyInfo]]) -> ProxyInfo:
        """프록시 설정 파싱"""
        if proxy_config is None:
            return ProxyInfo(url=None, enabled=False)
        elif isinstance(proxy_config, str):
            return ProxyInfo(url=proxy_config, enabled=True)
        elif isinstance(proxy_config, ProxyInfo):
            return proxy_config
        else:
            raise ValueError(f"잘못된 프록시 설정 타입: {type(proxy_config)}")

    def _validate_and_detect_proxy_type(self):
        """프록시 URL 유효성 검사 및 타입 감지"""
        if not self.config.url:
            self.config.proxy_type = None
            return

        try:
            parsed = urlparse(self.config.url)
            scheme = parsed.scheme.lower()

            # 프록시 타입 매핑
            proxy_type_mapping = {
                'http': ProxyType.HTTP,
                'https': ProxyType.HTTPS,
                'socks4': ProxyType.SOCKS4,
                'socks4a': ProxyType.SOCKS4A,
                'socks5': ProxyType.SOCKS5,
                'socks5h': ProxyType.SOCKS5H
            }

            if scheme not in proxy_type_mapping:
                raise ValueError(f"지원하지 않는 프록시 스키마: {scheme}")

            self.config.proxy_type = proxy_type_mapping[scheme]

        except Exception as e:
            raise ValueError(f"잘못된 프록시 URL: {e}")

    def _is_socks_proxy(self) -> bool:
        """SOCKS 프록시 여부 확인"""
        return self.config.proxy_type in [
            ProxyType.SOCKS4, ProxyType.SOCKS4A,
            ProxyType.SOCKS5, ProxyType.SOCKS5H
        ]

    def _is_http_proxy(self) -> bool:
        """HTTP 프록시 여부 확인"""
        return self.config.proxy_type in [ProxyType.HTTP, ProxyType.HTTPS]

    def _initialize_client(self) -> AsyncClient:
        """HTTPX 클라이언트 초기화"""
        ssl_context = ssl.create_default_context()
        ssl_context.set_ciphers(
            'ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AES:DHE+CHACHA20')
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED

        if hasattr(ssl, "TLSVersion"):
            ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3

        limits = Limits(max_keepalive_connections=5, max_connections=10)

        base_kwargs = {
            "http2": True,
            "follow_redirects": True,
            "verify": ssl_context,
            "limits": limits,
            **self.client_kwargs
        }

        if not self.config.enabled or not self.config.url:
            # 프록시 없이 직접 연결
            self.client = AsyncClient(**base_kwargs)
        elif self._is_socks_proxy():
            # SOCKS 프록시 사용 (httpx-socks 라이브러리)
            try:
                transport = AsyncProxyTransport.from_url(self.config.url)
                self.client = AsyncClient(transport=transport, **base_kwargs)
            except ImportError:
                raise ImportError(
                    "SOCKS 프록시를 사용하려면 httpx-socks 라이브러리가 필요합니다: "
                    "pip install httpx-socks"
                )

        elif self._is_http_proxy():
            # HTTP 프록시 사용 (httpx 내장 지원)
            self.client = AsyncClient(proxy=self.config.url, **base_kwargs)

        else:
            raise ValueError(f"알 수 없는 프록시 타입: {self.config.proxy_type}")

    def _get_default_headers(self, url, is_xhr=False):
        """기본 헤더 생성"""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Priority': 'u=0, i',
            'Upgrade-Insecure-Requests': '1',
        }

        # AJAX/XHR 요청인 경우 헤더 조정
        if is_xhr:
            headers.update({
                'Accept': 'application/json, text/plain, */*',
                'X-Requested-With': 'XMLHttpRequest',
                'referer': 'https://brand.naver.com/sisem/products/2237948335',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'TE': 'trailers'
            })

        # URL 파싱하여 Host, Origin 설정 (모든 요청에 적용하는 것이 좋음)
        parsed_url = urllib.parse.urlparse(url)
        hostname = parsed_url.netloc  # 예: 'brand.naver.com' 또는 'www.google.com'
        scheme = parsed_url.scheme    # 예: 'https'

        if hostname:
            headers['Host'] = hostname  # Host 헤더는 항상 포함하는 것이 좋음
        if is_xhr and scheme and hostname:  # CORS 관련 헤더는 XHR 시 주로 필요
            headers['Origin'] = f"{scheme}://{hostname}"
            # Referer도 필요시 설정 (예: headers['Referer'] = url)

        # --- 도메인 조건부 쿠키 설정 로직 ---

        # 1. 요청 URL의 도메인이 naver.com 또는 하위 도메인인지 확인
        is_naver_domain = hostname.endswith(
            '.naver.com') or hostname == 'naver.com'

        # 2. CookieManager에서 해당 URL의 쿠키 가져오기
        cookie_header_from_manager = self.cookie_manager.get_cookie_header(url)

        # 3. 도메인 조건 및 쿠키 상태에 따라 Cookie 헤더 설정
        if is_naver_domain:
            # 네이버 관련 도메인일 경우: 초기 쿠키 주입 로직 적용
            initial_cookie = None

            if self.use_playwright_cookies:
                # Playwright 쿠키 사용 시: store_token만 추가 (ini 쿠키 중복 방지)
                if self.store_token:
                    initial_cookie = f'X-Wtm-Cpt-Tk={self.store_token}; ba.uuid=0'
            else:
                # ini 설정 쿠키 사용 시: 전체 쿠키 추가
                if self.store_nnb and self.store_fwb and self.store_buc and self.store_token:
                    initial_cookie = f'NNB={self.store_nnb}; BUC={self.store_buc}; _fwb={self.store_fwb}; X-Wtm-Cpt-Tk={self.store_token}; ba.uuid=0'
                elif self.store_token:
                    initial_cookie = f'X-Wtm-Cpt-Tk={self.store_token}; ba.uuid=0'

            if cookie_header_from_manager:
                # CookieManager 쿠키가 있는 경우
                if initial_cookie and 'ba.uuid' not in cookie_header_from_manager:
                    # 초기 쿠키가 있고 ba.uuid가 없으면 앞에 추가
                    headers['Cookie'] = f"{initial_cookie}; {cookie_header_from_manager}"
                else:
                    # CookieManager 쿠키 우선 사용
                    headers['Cookie'] = cookie_header_from_manager
            elif initial_cookie:
                # CookieManager 쿠키가 없고 초기 쿠키가 있으면 초기 쿠키만 설정
                headers['Cookie'] = initial_cookie
        else:
            # 네이버 관련 도메인이 아닐 경우: CookieManager의 쿠키만 사용
            if cookie_header_from_manager:
                headers['Cookie'] = cookie_header_from_manager
            # else: CookieManager에도 쿠키가 없으면 Cookie 헤더를 보내지 않음

        # headers['Cookie'] = "wcs_bt=s_1d3cf0f9537ba:1751426189; NNB=UOOCBNBTR5SGQ; _fwb=125PUBMq60WT6bm5mpc7lLa.1751422131538; BUC=i61i96q5KMPBKTEZdRxKhAsArKssAvwm3wANujHMSWs="
        return headers

    def update_user_agent(self, new_agent):
        """
        User Agent 를 업데이트하는 메서드

        Args:
            new_agent (str): 새로운 User Agent 문자열
        """
        self.user_agent = new_agent

    def update_store_token(self, new_token):
        """
        Store token을 업데이트하는 메서드

        Args:
            new_token (str): 새로운 스토어 토큰
        """
        self.store_token = new_token

    async def get(self, url, **kwargs):
        """GET 요청 수행"""
        headers = kwargs.pop('headers', {})
        default_headers = self._get_default_headers(url)
        # 기본 헤더를 사용자 지정 헤더로 덮어쓰기
        default_headers.update(headers)

        response = await self.client.get(url, headers=default_headers, **kwargs)
        for resp_in_history in response.history:
            # 각 리다이렉션 응답의 URL을 기준으로 쿠키 업데이트 시도
            # httpx 응답 객체의 URL은 URL 객체이므로 문자열로 변환합니다.
            redirect_url = str(resp_in_history.url)
            self.cookie_manager.update_from_response(
                resp_in_history, redirect_url)

        # 최종 응답에서 쿠키 업데이트
        # 최종 응답의 URL은 response.url을 사용하거나, 초기 요청 url을 사용합니다.
        # 여기서는 초기 요청 url을 기준으로 업데이트합니다. (서버 동작에 따라 달라질 수 있음)
        self.cookie_manager.update_from_response(response, url)
        return response

    async def post(self, url, data=None, json_data=None, referer=None, **kwargs):  # referer 파라미터 추가
        """
        POST 요청 수행 (Referer 헤더 지정 가능)

        Args:
            url (str): 요청할 URL
            data (Optional[dict, str, bytes]): form 데이터 (application/x-www-form-urlencoded)
            json_data (Optional[Any]): JSON 데이터 (application/json)
            referer (Optional[str]): 명시적으로 설정할 Referer 헤더 값
            **kwargs: headers 등 httpx.AsyncClient.post에 전달될 추가 인자
        """
        # 1. 사용자 정의 헤더 추출 (kwargs에서)
        headers = kwargs.pop('headers', {})
        is_json = json_data is not None

        # 2. 기본 헤더 생성 (_get_default_headers 호출)
        #    _get_default_headers에서 설정된 기본 Referer가 있을 수 있음
        default_headers = self._get_default_headers(
            url, is_xhr=True)  # POST는 보통 XHR로 간주

        # 3. kwargs에서 추출한 사용자 정의 헤더 병합 (kwargs의 헤더가 기본 헤더 덮어씀)
        default_headers.update(headers)

        # 4. 'referer' 파라미터로 값이 명시적으로 전달된 경우, 헤더에 설정 (최우선 적용)
        if referer is not None:  # None이나 빈 문자열이 아닌 경우 설정
            default_headers['Referer'] = referer

        # 5. Content-Type 설정 (기존 로직 개선)
        #    사용자가 headers={'Content-Type': ...} 로 명시하지 않은 경우만 자동 설정
        content_type_set = 'Content-Type' in default_headers
        if not content_type_set:
            if is_json:
                default_headers['Content-Type'] = 'application/json;charset=UTF-8'
            elif data:
                # data가 dict 형태일 때만 기본으로 urlencoded 설정
                # data가 문자열/바이트면 사용자가 Content-Type을 지정해야 할 수 있음
                if isinstance(data, dict):
                    default_headers['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8'

        # 6. 요청 본문(content) 준비 및 Content-Length 설정 (기존 로직 개선)
        content_to_send = None
        if is_json:
            # separators 기본값이 (',', ': ') 이므로 불필요한 공백 제거 위해 명시
            # ensure_ascii=False 로 유니코드 문자 유지
            json_str = json.dumps(
                json_data, ensure_ascii=False, separators=(',', ':'))
            content_to_send = json_str.encode('utf-8')
            if 'Content-Length' not in default_headers:
                default_headers['Content-Length'] = str(len(content_to_send))
        elif isinstance(data, dict):
            # dict 데이터를 urlencode하여 utf-8 바이트로 변환
            content_to_send = urllib.parse.urlencode(
                data, encoding='utf-8').encode('utf-8')
            if 'Content-Length' not in default_headers:
                default_headers['Content-Length'] = str(len(content_to_send))
        elif isinstance(data, str):
            # 문자열 데이터는 utf-8 바이트로 인코딩
            content_to_send = data.encode('utf-8')
            if 'Content-Length' not in default_headers:
                default_headers['Content-Length'] = str(len(content_to_send))
        elif data is not None:  # bytes 등 다른 타입일 경우 그대로 사용
            content_to_send = data
            # Content-Length는 httpx가 계산하거나 사용자가 직접 설정해야 할 수 있음

        # 디버깅: 최종 요청 헤더 확인
        # print(f"--- Final POST Headers for {url} ---")
        # print(default_headers)
        # print("-" * 30)

        # 7. httpx 클라이언트로 POST 요청 전송
        response = await self.client.post(url, content=content_to_send, headers=default_headers, **kwargs)

        # 8. 응답에서 쿠키 추출하여 저장 (리다이렉션 포함)
        for resp_in_history in response.history:
            redirect_url = str(resp_in_history.url)
            self.cookie_manager.update_from_response(
                resp_in_history, redirect_url)
        self.cookie_manager.update_from_response(response, url)

        return response

    def get_playwright_cookies(self, url: str) -> List[Dict]:
        """Playwright에 전달할 쿠키를 생성합니다

        CookieManager의 쿠키와 초기 쿠키(store_nnb, store_fwb, store_buc)를 결합하여
        Playwright 형식으로 반환합니다.

        Args:
            url: 쿠키를 가져올 URL

        Returns:
            Playwright 형식의 쿠키 리스트
        """
        # CookieManager에서 기존 쿠키 가져오기
        playwright_cookies = self.cookie_manager.get_cookies_for_playwright(
            url)

        # 도메인 확인
        parsed_url = urllib.parse.urlparse(url)
        hostname = parsed_url.netloc
        is_naver_domain = hostname.endswith(
            '.naver.com') or hostname == 'naver.com'

        if is_naver_domain:
            # 기존 쿠키 이름 목록
            existing_cookie_names = {cookie['name']
                                     for cookie in playwright_cookies}

            # 초기 쿠키 추가 (중복되지 않은 경우만)
            if self.store_nnb and 'NNB' not in existing_cookie_names:
                playwright_cookies.append({
                    'name': 'NNB',
                    'value': self.store_nnb,
                    'domain': '.naver.com',
                    'path': '/',
                    'httpOnly': False,
                    'secure': True,
                    'sameSite': 'Lax'
                })

            if self.store_fwb and '_fwb' not in existing_cookie_names:
                playwright_cookies.append({
                    'name': '_fwb',
                    'value': self.store_fwb,
                    'domain': '.naver.com',
                    'path': '/',
                    'httpOnly': False,
                    'secure': True,
                    'sameSite': 'Lax'
                })

            if self.store_buc and 'BUC' not in existing_cookie_names:
                playwright_cookies.append({
                    'name': 'BUC',
                    'value': self.store_buc,
                    'domain': '.naver.com',
                    'path': '/',
                    'httpOnly': True,
                    'secure': True,
                    'sameSite': 'Lax'
                })

            if self.store_token and 'X-Wtm-Cpt-Tk' not in existing_cookie_names:
                playwright_cookies.append({
                    'name': 'X-Wtm-Cpt-Tk',
                    'value': self.store_token,
                    'domain': '.naver.com',
                    'path': '/',
                    'httpOnly': False,
                    'secure': True,
                    'sameSite': 'Lax'
                })

            # ba.uuid 쿠키 추가 (항상)
            if 'ba.uuid' not in existing_cookie_names:
                playwright_cookies.append({
                    'name': 'ba.uuid',
                    'value': '0',
                    'domain': '.naver.com',
                    'path': '/',
                    'httpOnly': False,
                    'secure': False,
                    'sameSite': 'Lax'
                })

        return playwright_cookies

    async def close(self):
        """클라이언트 종료"""
        if self.client:
            await self.client.aclose()


def find_pattern_in_list(data_list, original_pattern, token='*'):
    '''
    data_list 에서 pattern 을 검색하는 함수
    data_list : pattern 을 검색할 문장이 들어있는 리스트
    original_pattern : 검색할 패턴
    '''

    results = []

    # token가 하나 이상인 부분을 하나의 token로 치환
    escaped_token = re.escape(token)
    modified_pattern, star_replacements = re.subn(
        fr'{escaped_token}{{2,}}', token, original_pattern)

    # token 문자 앞뒤의 공백 제거
    pattern = re.sub(
        fr'\s*{escaped_token}\s*', token, modified_pattern)

    # 검색방향 확인
    isOneside = pattern.startswith(token) or pattern.endswith(token)

    if isOneside:
        # token가 패턴의 시작에 있을 때 처리 로직
        if pattern.startswith(token):
            if star_replacements > 0:
                pattern = r'(?:^)(.*)' + re.escape(pattern[1:])
            else:
                direction = 'left'
                pattern = re.escape(pattern[1:])
        # token가 패턴의 끝에 있을 때 처리 로직
        elif pattern.endswith(token):
            if star_replacements > 0:
                pattern = re.escape(pattern[:-1]) + r'(.*)'
            else:
                direction = 'right'
                pattern = re.escape(pattern[:-1])
        # 특수문자(…) 검색 조건 처리
        pattern = pattern.replace('...', r'(\.{3}|…)')

        for item in data_list:
            if isinstance(item, str):
                if star_replacements > 0:
                    normalize_item = normalize_spaces(item.strip())
                    matches = re.finditer(
                        pattern, normalize_item, re.IGNORECASE | re.DOTALL)
                    for match in matches:
                        # 첫 번째 그룹을 결과에 추가
                        if match.group(1).strip():
                            results.append(match.group(
                                1).strip().replace('…', '...'))
                else:
                    found_results = False  # 결과 발견 여부를 추적

                    for split_item in item.split('\n'):
                        normalize_item = normalize_spaces(split_item.strip())
                        current_results = extract_strings_before_keyword(
                            normalize_item, pattern, direction)

                        for current_result in current_results:
                            results.append(current_result)
                            if len(current_result) > 1:
                                found_results = True  # 1글자 이상 결과가 발견되었음을 표시

                        results += extract_strings_before_keyword(
                            normalize_item, pattern, direction)
                    # 줄바꿈을 무시하고 전체 문자열에 대해 다시 검색
                    if not found_results:
                        normalize_item = normalize_spaces(item.strip())
                        results += extract_strings_before_keyword(
                            normalize_item, pattern, direction)

    else:
        parts = pattern.split(token)
        # 역순으로 된 패턴1과 정상적인 패턴2를 생성합니다.
        pattern1 = re.escape(parts[0]).replace('...', r'(\.{3}|…)')
        pattern2 = re.escape(parts[1]).replace('...', r'(\.{3}|…)')

        for item in data_list:
            if isinstance(item, str):
                normalize_item = normalize_spaces(item.strip())
                # 패턴2에 대한 모든 매칭 위치를 찾습니다.
                for match in re.finditer(pattern2, normalize_item, re.IGNORECASE):
                    start_index = match.start()

                    # pattern2 시작점 이전에 있는 모든 pattern1 매칭을 찾습니다.
                    match1_positions = [m for m in re.finditer(
                        pattern1, normalize_item[:start_index], re.IGNORECASE)]

                    while match1_positions:
                        last_match1 = match1_positions.pop()
                        last_match1_end = last_match1.end()

                        # pattern1과 pattern2 사이의 텍스트를 추출합니다.
                        matched_text = normalize_item[last_match1_end:start_index].strip(
                        )

                        if matched_text:
                            results.append(matched_text.replace('…', '...'))
                            break

    return results


async def get_place_review(place_url, placeID, businessID, businessType, cidList, cnt, interval, client, progress_bar: tqdm):
    '''
    리뷰 가져오기
    place_url : 가게 url
    placeID : 가게 ID
    businessType : 구분
    cidList : base info 의 cidList
    cnt : 가져올 갯수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    global dataInfo, proxyInfo

    async def collect_data(reviewSort=None):
        '''
        데이터를 수집하는 함수
        reviewSort : 정렬방법, 최신순은 recent
        '''
        nonlocal dataDict, client, progress_bar

        if reviewSort:
            dataDict[0]['variables']['input']['sort'] = reviewSort
        result = []
        isSuccess = False
        review_offset = 0
        businessID = 0
        current_progress = progress_bar.n
        # 리뷰를 가져옴
        for i in range(1, cnt + 1):
            dataDict[0]['variables']['input']['page'] = i
            should_break = False  # 외부 for 루프를 제어하기 위한 변수
            try_count = 0  # 시도 횟수를 카운트하기 위한 변수
            while try_count < 3:
                try:
                    # debug code
                    response = await client.post('https://api.place.naver.com/graphql', json_data=dataDict, referer=place_url)
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_place_review : {place_url}\n{msg}', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_place_review : {response.status_code} error', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_place_review : {response.status_code}', False))
                        isSuccess = True
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code != 200:
                        try_count += 1
                        # 300ms 대기
                        await asyncio.sleep(dataInfo.errInterval*try_count**2)
                        continue
                    result_json = response.json()
                    if not bool(result_json[0]['data']['visitorReviews']['items']):
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = result_json[0]['data']['visitorReviews']['total'] == 0
                        break
                    review_offset += len(result_json[0]
                                         ['data']['visitorReviews']['items'])
                    result += extract_values(result_json[0],
                                             ['nickname', 'body'])
                    # businessID 확인
                    # if businessType == 'hairshop' and 'reply' in result_json[0]['data']['visitorReviews']['items'][0]:
                    #     bookingURL = result_json[0]['data']['visitorReviews']['items'][0]['reply']['editUrl']
                    #     # 정규 표현식을 사용하여 ID 추출
                    #     match = re.search(
                    #         r'booking/([^/]+)/reviews', bookingURL)
                    #     if match:
                    #         businessID = match.group(1)
                    if result_json[0]['data']['visitorReviews']['total'] == review_offset:
                        # 모든 리뷰를 가지고 왔을 경우
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                    break  # while 루프 탈출
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    try_count += 1
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    try_count += 1
                    asyncio.create_task(writelog(msg, False))
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break  # while 루프 탈출

            # 진행률 계산
            target_progress = current_progress + (i+1)*12.5 / cnt
            difference = target_progress - progress_bar.n
            difference_int = int(difference)
            # 진행률 막대를 목표 진행률로 업데이트합니다.
            progress_bar.update(difference_int)
            remaining_seconds = progress_bar._time() - progress_bar.start_t
            if progress_bar.n == 0:
                remaining_time = "알 수 없음"
            else:
                remaining_seconds = remaining_seconds * \
                    (progress_bar.total - progress_bar.n) / progress_bar.n
                remaining_time = format_time(remaining_seconds)
            dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
            dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

            if should_break:  # for 루프를 탈출해야 하는 경우
                break
            await asyncio.sleep(interval)
        else:
            # 수집 횟수를 모두 채우면 성공
            isSuccess = True

        return list(dict.fromkeys(result)), isSuccess

    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }
    # review dict
    dataDict = [
        {
            "operationName": "getVisitorReviews",
            "variables": {
                "input": {
                    "bookingBusinessId": businessID,
                    "businessId": placeID,
                    "businessType": businessType,
                    "item": "0",
                    "page": 0,
                    "size": 10,
                    "isPhotoUsed": False,
                    "includeContent": True,
                    "cidList": cidList,
                    "getUserStats": False,
                    "includeReceiptPhotos": False,
                    "getReactions": False,
                    "getTrailer": False
                },
                "id": placeID
            },
            "query": "query getVisitorReviews($input: VisitorReviewsInput) {\n  visitorReviews(input: $input) {\n    items {\n      id\n      rating\n      author {\n        id\n        nickname\n        from\n        imageUrl\n        borderImageUrl\n        objectId\n        url\n        review {\n          totalCount\n          imageCount\n          avgRating\n          __typename\n        }\n        theme {\n          totalCount\n          __typename\n        }\n        isFollowing\n        followerCount\n        followRequested\n        __typename\n      }\n      body\n      thumbnail\n      media {\n        type\n        thumbnail\n        thumbnailRatio\n        class\n        videoId\n        videoUrl\n        trailerUrl\n        __typename\n      }\n      tags\n      status\n      visitCount\n      viewCount\n      visited\n      created\n      reply {\n        editUrl\n        body\n        editedBy\n        created\n        date\n        replyTitle\n        isReported\n        isSuspended\n        __typename\n      }\n      originType\n      item {\n        name\n        code\n        options\n        __typename\n      }\n      language\n      highlightOffsets\n      apolloCacheId\n      translatedText\n      businessName\n      showBookingItemName\n      bookingItemName\n      votedKeywords {\n        code\n        iconUrl\n        iconCode\n        displayName\n        __typename\n      }\n      userIdno\n      loginIdno\n      receiptInfoUrl\n      reactionStat {\n        id\n        typeCount {\n          name\n          count\n          __typename\n        }\n        totalCount\n        __typename\n      }\n      hasViewerReacted {\n        id\n        reacted\n        __typename\n      }\n      nickname\n      showPaymentInfo\n      visitKeywords {\n        category\n        keywords\n        __typename\n      }\n      __typename\n    }\n    starDistribution {\n      score\n      count\n      __typename\n    }\n    hideProductSelectBox\n    total\n    showRecommendationSort\n    itemReviewStats {\n      score\n      count\n      itemId\n      starDistribution {\n        score\n        count\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}"
        }
    ]

    # 추천순
    result_ranking, isSuccess_ranking = await collect_data()

    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 37 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    # 최신순
    result_recent, isSuccess_recent = await collect_data("recent")

    return list(dict.fromkeys(result_ranking+result_recent)), isSuccess_ranking & isSuccess_recent


async def get_place_blog(place_url, placeID, businessType, cnt, interval, client, progress_bar: tqdm):
    '''
    블로그 가져오기
    placeID : 가게 ID
    businessType : 구분
    cnt : 가져올 갯수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    global dataInfo

    async def collect_data(reviewSort=None):
        '''
        데이터를 수집하는 함수
        reviewSort : 정렬방법, 최신순은 recent
        '''
        nonlocal dataDict, client, progress_bar

        if reviewSort:
            dataDict[0]['variables']['input']['reviewSort'] = reviewSort
        result = []
        isSuccess = False
        blog_offset = 0
        current_progress = progress_bar.n

        # 블로그를 가져옴
        for i in range(0, cnt):
            dataDict[0]['variables']['input']['page'] = i
            should_break = False  # 외부 for 루프를 제어하기 위한 변수
            try_count = 0  # 시도 횟수를 카운트하기 위한 변수
            while try_count < 3:  # 최대 2번까지 시도
                try:
                    response = await client.post('https://api.place.naver.com/graphql', json_data=dataDict, referer=place_url)
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_place_blog : {place_url}\n{msg}', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_place_blog : {response.status_code} error', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_place_blog : {response.status_code}', False))
                        isSuccess = True
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code != 200:
                        try_count += 1  # 시도 횟수 증가
                        await asyncio.sleep(dataInfo.errInterval*try_count**2)
                        continue
                    result_json = response.json()
                    if not bool(result_json[0]['data']['fsasReviews']['items']):
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = result_json[0]['data']['fsasReviews']['total'] == 0
                        break
                    blog_offset += len(result_json[0]
                                       ['data']['fsasReviews']['items'])
                    result += extract_values(result_json[0],
                                             ['authorName', 'name', 'title', 'contents'])
                    if result_json[0]['data']['fsasReviews']['maxItemCount'] == blog_offset:
                        # 모든 리뷰를 가지고 왔을 경우
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                    break  # while 루프 탈출
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    try_count += 1  # 시도 횟수 증가
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    try_count += 1
                    asyncio.create_task(writelog(msg, False))
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break  # while 루프 탈출
            if should_break:  # for 루프를 탈출해야 하는 경우
                break
            await asyncio.sleep(interval)

            # 진행률 계산
            target_progress = current_progress + (i+1)*12.5 / cnt
            difference = target_progress - progress_bar.n
            difference_int = int(difference)
            # 진행률 막대를 목표 진행률로 업데이트합니다.
            progress_bar.update(difference_int)
            remaining_seconds = progress_bar._time() - progress_bar.start_t
            if progress_bar.n == 0:
                remaining_time = "알 수 없음"
            else:
                remaining_seconds = remaining_seconds * \
                    (progress_bar.total - progress_bar.n) / progress_bar.n
                remaining_time = format_time(remaining_seconds)
            dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
            dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time
        else:
            # 수집 횟수를 모두 채우면 성공
            isSuccess = True

        return list(dict.fromkeys(result)), isSuccess

    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }
    #
    # blog dict
    dataDict = [
        {
            "operationName": "getFsasReviews",
            "variables": {
                "input": {
                    "businessId": placeID,
                    "businessType": businessType,
                    "page": 0,
                    "display": 10,
                    "deviceType": "mobile",
                    "query": "",
                    "excludeGdids": []
                }
            },
            "query": "query getFsasReviews($input: FsasReviewsInput) {\n  fsasReviews(input: $input) {\n    ...FsasReviews\n    __typename\n  }\n}\n\nfragment FsasReviews on FsasReviewsResult {\n  total\n  maxItemCount\n  items {\n    name\n    type\n    typeName\n    url\n    home\n    id\n    title\n    rank\n    contents\n    bySmartEditor3\n    hasNaverReservation\n    thumbnailUrl\n    thumbnailUrlList\n    thumbnailCount\n    date\n    isOfficial\n    isRepresentative\n    profileImageUrl\n    isVideoThumbnail\n    reviewId\n    authorName\n    createdString\n    bypassToken\n    __typename\n  }\n  __typename\n}"
        }
    ]

    # 추천순
    result_ranking, isSuccess_ranking = await collect_data()

    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 62 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    # 최신순
    result_recent, isSuccess_recent = await collect_data("recent")

    return list(dict.fromkeys(result_ranking+result_recent)), isSuccess_ranking & isSuccess_recent


async def get_place_feed(place_url, placeID, naverBlog, cnt, interval, client, progress_bar: tqdm):
    '''
    소식 가져오기
    place_url : 가게 url
    placeID : 가게 ID
    naverBlog : base info 의 naverBlog
    cnt : 가져올 갯수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }
    # feed dict, 소식
    dataDict = [
        {
            "operationName": "getFeeds",
            "variables": {
                "businessId": placeID,
                "blogId": naverBlog.get('id', "") if bool(naverBlog) else "",
                "blogCategoryNo": naverBlog.get('categoryNo', "") if bool(naverBlog) else "",
                "type": "all",
                "feedOffset": 0,
                "blogOffset": 0
            },
            "query": "query getFeeds($businessId: String!, $blogId: String, $blogCategoryNo: String, $type: String, $feedOffset: Int, $blogOffset: Int) {\n  feeds(\n    businessId: $businessId\n    blogId: $blogId\n    blogCategoryNo: $blogCategoryNo\n    type: $type\n    feedOffset: $feedOffset\n    blogOffset: $blogOffset\n  ) {\n    feeds {\n      ...FeedFields\n      blogId\n      __typename\n    }\n    hasMore\n    blogInfo {\n      id\n      categoryNo\n      nickname\n      imageUrl\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment FeedFields on Feed {\n  type\n  feedId\n  title\n  desc\n  category\n  period\n  media {\n    mediaType\n    thumbnail\n    thumbnailRatio\n    videoUrl\n    header {\n      vid\n      duration\n      __typename\n    }\n    trailerUrl\n    music {\n      title\n      artists\n      __typename\n    }\n    __typename\n  }\n  isDeleted\n  isPinned\n  relativeCreated\n  createdString\n  blogId\n  id\n  isLikeEnabled\n  thumbnail {\n    url\n    isVideo\n    __typename\n  }\n  __typename\n}"
        }
    ]
    current_progress = progress_bar.n
    feed_result = []
    feed_offset = 0
    blog_result = []
    blog_offset = 0
    result = []
    isSuccess = False
    # feed를 가져옴
    for i in range(0, cnt):
        dataDict[0]['variables']['feedOffset'] = feed_offset
        dataDict[0]['variables']['blogOffset'] = blog_offset
        should_break = False  # 외부 for 루프를 제어하기 위한 변수
        try_count = 0  # 시도 횟수를 카운트하기 위한 변수
        while try_count < 3:  # 최대 2번까지 시도
            try:
                # debug code
                # print(f'get_place_feed : {place_url}')
                response = await client.post('https://api.place.naver.com/graphql', json_data=dataDict, referer=place_url)
                if response.status_code == 429:
                    # 429 Too Many Requests
                    msg = response.text
                    asyncio.create_task(
                        writelog(f'get_place_feed : {place_url}\n{msg}', False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break
                elif 500 <= response.status_code < 600:
                    asyncio.create_task(
                        writelog(f'get_place_feed : {response.status_code} error', False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break
                elif response.status_code == 204:
                    # 204 No Content
                    asyncio.create_task(
                        writelog(f'get_place_feed : {response.status_code}', False))
                    isSuccess = True
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break
                elif response.status_code != 200:
                    try_count += 1  # 시도 횟수 증가
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                result_json = response.json()
                for feed in result_json[0]['data']['feeds']['feeds']:
                    if feed['type'] == "FEED":
                        feed_result += extract_values(feed,
                                                      ['title', 'desc'])
                        if feed['isPinned'] == False:
                            feed_offset += 1
                    elif feed['type'] == "BLOG":
                        blog_result += extract_values(feed,
                                                      ['title', 'desc'])
                        if feed['isPinned'] == False:
                            blog_offset += 1
                    else:
                        msg = f"feed 에서 type 분류 실패! : {feed}"
                        asyncio.create_task(writelog(msg, False))
                if not result_json[0]['data']['feeds']['hasMore']:
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    isSuccess = True
                    break
                break  # while 루프 탈출
            except json.decoder.JSONDecodeError:
                msg = response.text
                asyncio.create_task(writelog(msg, False))
                try_count += 1  # 시도 횟수 증가
                await asyncio.sleep(dataInfo.errInterval*try_count**2)
                continue
            except TypeError:
                msg = response.text
                msg += f'{traceback.format_exc()}'
                try_count += 1
                asyncio.create_task(writelog(msg, False))
                break
            except RequestError as exc:
                msg = f'{traceback.format_exc()}'
                asyncio.create_task(writelog(msg, False))
                should_break = True  # for 루프를 탈출해야 함을 표시
                break  # while 루프 탈출

        # 진행률 계산
        target_progress = current_progress + (i+1)*20 / cnt
        difference = target_progress - progress_bar.n
        difference_int = int(difference)
        # 진행률 막대를 목표 진행률로 업데이트합니다.
        progress_bar.update(difference_int)
        remaining_seconds = progress_bar._time() - progress_bar.start_t
        if progress_bar.n == 0:
            remaining_time = "알 수 없음"
        else:
            remaining_seconds = remaining_seconds * \
                (progress_bar.total - progress_bar.n) / progress_bar.n
            remaining_time = format_time(remaining_seconds)
        dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
        dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

        if should_break:  # for 루프를 탈출해야 하는 경우
            break
        await asyncio.sleep(interval)
    else:
        # 수집 횟수를 모두 채우면 성공
        isSuccess = True

    result = feed_result+blog_result

    return result, isSuccess


async def get_place_location(place_url, placeID, businessType, client):
    '''
    지도 가져오기
    place_url : place 주소
    placeID : 가게 ID
    businessType : place type
    client : httpx
    '''
    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }
    # location
    dataDict = [
        {
            "operationName": "getBusiness",
            "variables": {
                "id": placeID,
                "businessType": businessType
            },
            "query": "query getBusiness($id: String!) {\n  business: placeDetail(input: {id: $id, isNx: false, deviceType: \"mobile\"}) {\n    base {\n      ...PlaceDetailBase\n      __typename\n    }\n    subwayStations {\n      ...SubwayStations\n      __typename\n    }\n    busStations {\n      ...BusStation\n      __typename\n    }\n    parkingLots {\n      ...ParkingLot\n      __typename\n    }\n    __typename\n  }\n  panoramaThumbnail(\n    input: {businessId: $id, width: 176, height: 116, type: sphere}\n  ) {\n    url\n    __typename\n  }\n}\n\nfragment PlaceDetailBase on PlaceDetailBase {\n  id\n  name\n  reviewSettings {\n    keyword\n    blog\n    cafe\n    showVisitorReviewScore\n    __typename\n  }\n  siteId\n  road\n  conveniences\n  category\n  categoryCode\n  categoryCodeList\n  defaultCategoryCodeList\n  categoryCount\n  rcode\n  roadAddress\n  address\n  streetPanorama {\n    id\n    pan\n    tilt\n    lon\n    lat\n    fov\n    __typename\n  }\n  isKtis\n  visitorReviewsTotal\n  visitorReviewsScore\n  missingInfo {\n    businessType\n    isBizHourMissing\n    isMenuImageMissing\n    isAccessorMissing\n    isDescriptionMissing\n    isConveniencesMissing\n    needLargeSuggestionBanner\n    isBoss\n    __typename\n  }\n  hideBusinessHours\n  hidePrice\n  microReviews\n  paymentInfo\n  openingHours {\n    day\n    isDayOff\n    schedule {\n      name\n      descriptions\n      isDayOff\n      __typename\n    }\n    __typename\n  }\n  isGoodStore\n  coordinate {\n    x\n    y\n    mapZoomLevel\n    __typename\n  }\n  poiInfo {\n    polyline {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      boundary {\n        minX\n        minY\n        maxX\n        maxY\n        __typename\n      }\n      details {\n        totalDistance\n        departureAddress\n        arrivalAddress\n        departureCoordX\n        departureCoordY\n        arrivalCoordX\n        arrivalCoordY\n        __typename\n      }\n      __typename\n    }\n    land {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      __typename\n    }\n    polygon {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      __typename\n    }\n    relation {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      details {\n        type\n        sid\n        fullName\n        name\n        category\n        x\n        y\n        __typename\n      }\n      __typename\n    }\n    parentRelation {\n      shapeType\n      __typename\n    }\n    __typename\n  }\n  menus {\n    priority\n    name\n    price\n    recommend\n    change\n    priceType\n    description\n    images\n    id\n    index\n    __typename\n  }\n  routeUrl\n  virtualPhone\n  phone\n  talktalkUrl\n  chatBotUrl\n  naverBlog {\n    id\n    categoryNo\n    __typename\n  }\n  visitorReviewsTextReviewTotal\n  __typename\n}\n\nfragment BusStation on BusStation {\n  id\n  name\n  displayCode\n  lat\n  lng\n  innerRoutes {\n    routeType {\n      type\n      typeName\n      innerRoute {\n        id\n        name\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  walkTime\n  walkingDistance\n  __typename\n}\n\nfragment ParkingLot on ParkingLot {\n  name\n  category\n  address\n  roadAddress\n  distance\n  lat\n  lng\n  placeId\n  description\n  __typename\n}\n\nfragment SubwayStations on SubwayStation {\n  no\n  name\n  type\n  typeDesc\n  color\n  priority\n  transfers {\n    no\n    name\n    type\n    color\n    priority\n    __typename\n  }\n  station {\n    id\n    name\n    lat\n    lng\n    nearestExit\n    nearestExitType\n    walkTime\n    walkingDistance\n    __typename\n  }\n  __typename\n}"
        }
    ]

    result = []
    cidList = None
    naverBlog = None
    coordinate = list()
    isSuccess = False
    try_count = 0  # 시도 횟수를 카운트하기 위한 변수
    while try_count < 3:
        try:
            # debug code
            response = await client.post('https://api.place.naver.com/graphql', json_data=dataDict, referer=place_url)
            if response.status_code == 429:
                # 429 Too Many Requests
                msg = response.text
                asyncio.create_task(
                    writelog(f'get_place_location : {place_url}\n{msg}', False))
                break
            elif 500 <= response.status_code < 600:
                asyncio.create_task(
                    writelog(f'get_place_location : {response.status_code} error', False))
                break
            elif response.status_code == 204:
                # 204 No Content
                asyncio.create_task(
                    writelog(f'get_place_location : {response.status_code}', False))
                isSuccess = True
                break
            elif response.status_code != 200:
                try_count += 1
                await asyncio.sleep(dataInfo.errInterval*try_count**2)
                continue
            result_json = response.json()
            result = extract_values(result_json[0], ['road'])
            # 메뉴
            if 'menus' in result_json[0]['data']['business']['base']:
                result += extract_values(result_json[0]['data']['business']['base']['menus'], [
                    'name', 'description'])
            # 주소
            if result_json[0]['data']['business']['base'].get('roadAddress', None):
                result += [result_json[0]['data']
                           ['business']['base']['roadAddress']]
            # 전화번호
            if result_json[0]['data']['business']['base'].get('virtualPhone', None):
                result += [result_json[0]['data']
                           ['business']['base']['virtualPhone']]
            # 좌표
            if 'coordinate' in result_json[0]['data']['business']['base']:
                coordinate.append(
                    result_json[0]['data']['business']['base']['coordinate']['x'])
                coordinate.append(
                    result_json[0]['data']['business']['base']['coordinate']['y'])
            # 편의시설
            if result_json[0]['data']['business']['base'].get('conveniences', None):
                result += [', '.join(result_json[0]['data']
                                     ['business']['base']['conveniences'])]

            if result_json[0]['data']['business']['base'].get('phone', None):
                result += [result_json[0]['data']
                           ['business']['base']['phone']]
            cidList = result_json[0]['data']['business']['base']['defaultCategoryCodeList']
            naverBlog = result_json[0]['data']['business']['base']['naverBlog']
            isSuccess = True
            break  # while 루프 탈출
        except json.decoder.JSONDecodeError:
            msg = response.text
            asyncio.create_task(writelog(msg, False))
            try_count += 1
            await asyncio.sleep(dataInfo.errInterval*try_count**2)
            continue
        except TypeError:
            msg = response.text
            msg += f'{traceback.format_exc()}'
            try_count += 1
            asyncio.create_task(writelog(msg, False))
            break
        except RequestError as exc:
            msg = f'{traceback.format_exc()}'
            asyncio.create_task(writelog(msg, False))
            break

    return result, cidList, naverBlog, coordinate, isSuccess


async def get_place_stylelist(place_url, businessID, businessType, session):
    '''
    스타일리스트 가져오기
    place_url : place 주소
    placeID : 가게 ID
    businessType : place type
    session : httpx
    '''
    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }
    # stylelist
    dataDict = [
        {
            "operationName": "getStylists",
            "variables": {
                "id": businessID,
                "businessType": businessType
            },
            "query": "query getStylists($id: String, $businessType: String, $startDate: String) {  bookingItems(    input: {bookingBusinessId: $id, businessType: $businessType, startDate: $startDate}  ) {    items {      id      businessId      name      isNPayUsed      postPaid      desc      precautionMessage      url      bookingUrl      imageUrl      type      bookingTimeUnit      __typename    }    __typename  }  visitorReviewStatsByBookingBusinessId(input: {bookingBusinessId: $id}) {    items {      id      itemId      score      count      __typename    }    __typename  }}query getBusiness($id: String!) {\n  business: placeDetail(input: {id: $id, isNx: false, deviceType: \"mobile\"}) {\n    base {\n      ...PlaceDetailBase\n      __typename\n    }\n    subwayStations {\n      ...SubwayStations\n      __typename\n    }\n    busStations {\n      ...BusStation\n      __typename\n    }\n    parkingLots {\n      ...ParkingLot\n      __typename\n    }\n    __typename\n  }\n  panoramaThumbnail(\n    input: {businessId: $id, width: 176, height: 116, type: sphere}\n  ) {\n    url\n    __typename\n  }\n}\n\nfragment PlaceDetailBase on PlaceDetailBase {\n  id\n  name\n  reviewSettings {\n    keyword\n    blog\n    cafe\n    showVisitorReviewScore\n    __typename\n  }\n  siteId\n  road\n  conveniences\n  category\n  categoryCode\n  categoryCodeList\n  defaultCategoryCodeList\n  categoryCount\n  rcode\n  roadAddress\n  address\n  streetPanorama {\n    id\n    pan\n    tilt\n    lon\n    lat\n    fov\n    __typename\n  }\n  isKtis\n  businessHours {\n    index\n    day\n    isDayOff\n    startTime\n    endTime\n    hourString\n    description\n    __typename\n  }\n  visitorReviewsTotal\n  visitorReviewsScore\n  missingInfo {\n    businessType\n    isBizHourMissing\n    isMenuImageMissing\n    isAccessorMissing\n    isDescriptionMissing\n    isConveniencesMissing\n    needLargeSuggestionBanner\n    isBoss\n    __typename\n  }\n  hideBusinessHours\n  hidePrice\n  microReviews\n  paymentInfo\n  openingHours {\n    day\n    isDayOff\n    schedule {\n      name\n      descriptions\n      isDayOff\n      __typename\n    }\n    __typename\n  }\n  isGoodStore\n  coordinate {\n    x\n    y\n    mapZoomLevel\n    __typename\n  }\n  poiInfo {\n    polyline {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      boundary {\n        minX\n        minY\n        maxX\n        maxY\n        __typename\n      }\n      details {\n        totalDistance\n        departureAddress\n        arrivalAddress\n        departureCoordX\n        departureCoordY\n        arrivalCoordX\n        arrivalCoordY\n        __typename\n      }\n      __typename\n    }\n    land {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      __typename\n    }\n    polygon {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      __typename\n    }\n    relation {\n      shapeType\n      shapeKey {\n        id\n        name\n        version\n        __typename\n      }\n      details {\n        type\n        sid\n        fullName\n        name\n        category\n        x\n        y\n        __typename\n      }\n      __typename\n    }\n    parentRelation {\n      shapeType\n      __typename\n    }\n    __typename\n  }\n  routeUrl\n  virtualPhone\n  phone\n  menus {\n    priority\n    name\n    price\n    recommend\n    change\n    priceType\n    description\n    images\n    id\n    index\n    __typename\n  }\n  talktalkUrl\n  chatBotUrl\n  naverBlog {\n    id\n    categoryNo\n    __typename\n  }\n  visitorReviewsTextReviewTotal\n  __typename\n}\n\nfragment BusStation on BusStation {\n  id\n  name\n  displayCode\n  lat\n  lng\n  innerRoutes {\n    routeType {\n      type\n      typeName\n      innerRoute {\n        id\n        name\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  walkTime\n  walkingDistance\n  __typename\n}\n\nfragment ParkingLot on ParkingLot {\n  name\n  category\n  address\n  roadAddress\n  distance\n  lat\n  lng\n  placeId\n  description\n  __typename\n}\n\nfragment SubwayStations on SubwayStation {\n  no\n  name\n  type\n  typeDesc\n  color\n  priority\n  transfers {\n    no\n    name\n    type\n    color\n    priority\n    __typename\n  }\n  station {\n    id\n    name\n    lat\n    lng\n    nearestExit\n    nearestExitType\n    walkTime\n    walkingDistance\n    __typename\n  }\n  __typename\n}"
        }
    ]

    result = []
    isSuccess = False
    try_count = 0  # 시도 횟수를 카운트하기 위한 변수
    while try_count < 3:
        try:
            response = await session.post('https://api.place.naver.com/graphql', headers=header, json_data=dataDict)
            if response.status_code == 429:
                # 429 Too Many Requests
                msg = response.text
                asyncio.create_task(
                    writelog(f'get_place_stylelist : {place_url}\n{msg}', False))
                break
            elif 500 <= response.status_code < 600:
                asyncio.create_task(
                    writelog(f'get_place_stylelist : {response.status_code} error', False))
                break
            elif response.status_code == 204:
                # 204 No Content
                asyncio.create_task(
                    writelog(f'get_place_stylelist : {response.status_code}', False))
                isSuccess = True
                break
            elif response.status_code != 200:
                try_count += 1
                await asyncio.sleep(dataInfo.errInterval*try_count**2)
                continue
            result_json = response.json()
            # 스타일리스트
            if 'items' in result_json[0]['data']['bookingItems']:
                result += extract_values(result_json[0]['data']['bookingItems']['items'], [
                    'name', 'desc'])
            isSuccess = True
            break  # while 루프 탈출
        except json.decoder.JSONDecodeError:
            msg = response.text
            asyncio.create_task(writelog(msg, False))
            try_count += 1
            await asyncio.sleep(dataInfo.errInterval*try_count**2)
            continue
        except TypeError:
            msg = response.text
            msg += f'{traceback.format_exc()}'
            try_count += 1
            asyncio.create_task(writelog(msg, False))
            break
        except RequestError as exc:
            msg = f'{traceback.format_exc()}'
            asyncio.create_task(writelog(msg, False))
            break

    return result, isSuccess


async def get_place_booking(place_url, businessID, businessType, client):
    '''
    예약정보 가져오기
    place_url : place 주소
    placeID : 가게 ID
    businessType : place type
    client : httpx
    '''
    html_header = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': dataInfo.User_Agent
    }

    json_header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }
    # booking
    dataDict = [
        {
            "operationName": "getBookingItems",
            "variables": {
                "bizItemTypes": [
                    "STANDARD"
                ],
                "id": businessID,
                "businessType": businessType,
                "realTimeBookingInput": {
                    "skipBookingItems": False
                },
                "timeout": 3000
            },
            "query": "query getBookingItems($id: String, $businessType: String, $bizItemTypes: [String], $realTimeBookingInput: RealTimeBookingInput, $timeout: Int) {\n  bookingItems(\n    input: {bookingBusinessId: $id, businessType: $businessType, bizItemTypes: $bizItemTypes, realTimeBookingInput: $realTimeBookingInput, timeout: $timeout}\n  ) {\n    items {\n      apolloCacheId\n      id\n      businessId\n      name\n      isNPayUsed\n      desc\n      bookingUrl\n      imageUrls\n      bizItemType\n      bizItemSubType\n      reviewStat {\n        score\n        count\n        __typename\n      }\n      originalBookingUrl\n      availableTime {\n        displayTime\n        keyTime\n        date\n        status\n        __typename\n      }\n      isRealTimeBooking\n      realTimeBookingDisabledDescription\n      minBookablePeopleCount\n      maxBookablePeopleCount\n      sameDayBookingTimeLimit\n      __typename\n    }\n    selectedRealTimeBookingFilter {\n      date\n      time\n      peopleNumber\n      __typename\n    }\n    __typename\n  }\n  visitorReviewStatsByBookingBusinessId(input: {bookingBusinessId: $id}) {\n    items {\n      id\n      itemId\n      score\n      count\n      __typename\n    }\n    __typename\n  }\n}"
        }
    ]

    result = []
    isSuccess = False
    try_count = 0  # 시도 횟수를 카운트하기 위한 변수
    while try_count < 3:
        try:
            # debug code
            # print(f'get_place_location : {place_url}')
            if businessID != "0":
                response = await client.post('https://api.place.naver.com/graphql', json_data=dataDict, referer=place_url)
                if response.status_code == 429:
                    # 429 Too Many Requests
                    msg = response.text
                    asyncio.create_task(
                        writelog(f'get_place_booking : {place_url}\n{msg}', False))
                    break
                elif 500 <= response.status_code < 600:
                    asyncio.create_task(
                        writelog(f'get_place_booking : {response.status_code} error', False))
                    break
                elif response.status_code == 204:
                    # 204 No Content
                    asyncio.create_task(
                        writelog(f'get_place_booking : {response.status_code}', False))
                    isSuccess = True
                    break
                elif response.status_code != 200:
                    try_count += 1
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                result_json = response.json()
                # 예약정보
                if 'items' in result_json[0]['data']['bookingItems']:
                    result += extract_values(result_json[0]['data']['bookingItems']['items'], [
                        'name', 'desc'])
                isSuccess = True
                break  # while 루프 탈출
            else:
                response = await client.get(f'{place_url.replace("home", "ticket")}', headers=html_header)
                if response.status_code == 429:
                    # 429 Too Many Requests
                    msg = response.text
                    asyncio.create_task(
                        writelog(f'get_place_booking : {place_url}\n{msg}', False))
                    break
                elif 500 <= response.status_code < 600:
                    asyncio.create_task(
                        writelog(f'get_place_booking : {place_url} : {response.status_code} error', False))
                    break
                elif response.status_code == 204:
                    # 204 No Content
                    asyncio.create_task(
                        writelog(f'get_place_booking : {response.status_code}', False))
                    isSuccess = True
                    break
                elif response.status_code != 200:
                    try_count += 1
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                html = response.text
                soup = bs(html, 'html.parser')
                ticket_content = soup.find('div', class_='zpUI7')
                if ticket_content:
                    result.append(ticket_content.text)
                isSuccess = True
                break  # while 루프 탈출
        except json.decoder.JSONDecodeError:
            msg = response.text
            asyncio.create_task(writelog(msg, False))
            try_count += 1
            await asyncio.sleep(dataInfo.errInterval*try_count**2)
            continue
        except TypeError:
            msg = response.text
            msg += f'{traceback.format_exc()}'
            try_count += 1
            asyncio.create_task(writelog(msg, False))
            break
        except RequestError as exc:
            msg = f'{traceback.format_exc()}'
            asyncio.create_task(writelog(msg, False))
            break

    return result, isSuccess


async def get_place_arround(place_url, placeID, base_coordinate, cnt, interval, client, progress_bar: tqdm):
    '''
    주변 정보 가져오기
    place_url : 가게 url
    placeID : 가게 ID
    base_coordinate : 좌표
    cnt : 가져올 갯수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    async def collect_data(theme):
        '''
        데이터를 수집하는 함수
        theme : 수집할 테마
        '''
        nonlocal dataDict, client, progress_bar

        dataDict[0]['variables']['input']['theme'] = theme

        current_progress = progress_bar.n
        arround_result = []
        start_offset = 1
        isSuccess = False
        # arround를 가져옴
        for i in range(0, cnt):
            dataDict[0]['variables']['input']['start'] = start_offset
            should_break = False  # 외부 for 루프를 제어하기 위한 변수
            try_count = 0  # 시도 횟수를 카운트하기 위한 변수
            while try_count < 3:  # 최대 2번까지 시도
                try:
                    response = await client.post('https://api.place.naver.com/graphql', client, json_data=dataDict, referer=place_url)
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_place_arround : {place_url}\n{msg}', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_place_arround : {response.status_code} error', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_place_arround : {response.status_code}', False))
                        isSuccess = True
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code != 200:
                        try_count += 1  # 시도 횟수 증가
                        await asyncio.sleep(dataInfo.errInterval*try_count**2)
                        continue
                    result_json = response.json()
                    for arround in result_json[0]['data']['trips']['items']:
                        arround_str = extract_values(
                            arround, ['authorName', 'name', 'category'], isMerge=True)
                        arround_info = arround_str[0].split('\n')
                        arround_latters = convertToInitialLetters(
                            arround_info[1])
                        arround_info.insert(1, arround_latters)
                        arround_result += ['\n'.join(arround_info)]
                        start_offset += 1
                    if start_offset > result_json[0]['data']['trips']['total']:
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                        break
                    break  # while 루프 탈출
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    try_count += 1  # 시도 횟수 증가
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    try_count += 1
                    asyncio.create_task(writelog(msg, False))
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break  # while 루프 탈출

            # 진행률 계산
            target_progress = current_progress + (i+1)*5 / cnt
            difference = target_progress - progress_bar.n
            difference_int = int(difference)
            # 진행률 막대를 목표 진행률로 업데이트합니다.
            progress_bar.update(difference_int)
            remaining_seconds = progress_bar._time() - progress_bar.start_t
            if progress_bar.n == 0:
                remaining_time = "알 수 없음"
            else:
                remaining_seconds = remaining_seconds * \
                    (progress_bar.total - progress_bar.n) / progress_bar.n
                remaining_time = format_time(remaining_seconds)
            dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
            dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

            if should_break:  # for 루프를 탈출해야 하는 경우
                break
            await asyncio.sleep(interval)
        else:
            # 수집 횟수를 모두 채우면 성공
            isSuccess = True

        return list(dict.fromkeys(arround_result)), isSuccess

    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }
    # arround
    dataDict = [
        {
            "operationName": "getTrips",
            "variables": {
                "input": {
                    "businessId": placeID,
                    "coordinateFilter": 2,
                    "coordinateFilterDistance": 5000,
                    "display": 20,
                    "isAroundSearch": True,
                    "query": "가볼만한곳",
                    "start": 1,
                    "theme": "100",
                    "x": base_coordinate[0],
                    "y": base_coordinate[1]
                },
                "isNmap": False
            },
            "query": "query getTrips($input: TripsInput, $isNmap: Boolean!) {\n  trips(input: $input) {\n    total\n    isSubSearch\n    themes {\n      name\n      value\n      __typename\n    }\n    tags {\n      name\n      value\n      img\n      __typename\n    }\n    selectedFilter {\n      theme\n      tag\n      __typename\n    }\n    items {\n      ...TripItemFields\n      __typename\n    }\n    nlu {\n      queryResult {\n        region\n        spotid\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment TripItemFields on TripSummary {\n  id\n  apolloCacheId\n  name\n  x\n  y\n  distance\n  bookingUrl\n  categoryCodeList\n  address\n  roadAddress\n  commonAddress\n  promotionTitle\n  imageUrl\n  imageUrls\n  tags\n  microReview\n  blogCafeReviewCount\n  visitorReviewCount\n  contentReviewCount\n  category\n  dbType\n  virtualPhone\n  phone\n  hasBooking\n  hasNPay\n  bookingVisitId\n  bookingPickupId\n  isTableOrder\n  isPreOrder\n  isTakeOut\n  bookingBusinessId\n  talktalkUrl\n  isDelivery\n  isCvsDelivery\n  imageMarker @include(if: $isNmap) {\n    marker\n    markerSelected\n    __typename\n  }\n  markerId @include(if: $isNmap)\n  markerLabel @include(if: $isNmap) {\n    text\n    style\n    __typename\n  }\n  bookingDisplayName\n  bookingHubUrl\n  bookingHubButtonName\n  blogImages {\n    thumbnailUrl\n    postUrl\n    authorId\n    postNo\n    authorName\n    profileImageUrl\n    gdid\n    __typename\n  }\n  streetPanorama {\n    id\n    pan\n    tilt\n    lat\n    lon\n    __typename\n  }\n  newBusinessHours {\n    status\n    __typename\n  }\n  baemin {\n    businessHours {\n      deliveryTime {\n        start\n        end\n        __typename\n      }\n      closeDate {\n        start\n        end\n        __typename\n      }\n      temporaryCloseDate {\n        start\n        end\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  yogiyo {\n    businessHours {\n      actualDeliveryTime {\n        start\n        end\n        __typename\n      }\n      bizHours {\n        start\n        end\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  coupon {\n    total\n    promotions {\n      promotionSeq\n      couponSeq\n      conditionType\n      image {\n        url\n        __typename\n      }\n      title\n      description\n      type\n      couponUseType\n      __typename\n    }\n    __typename\n  }\n  newOpening\n  contents {\n    type\n    id\n    title\n    description\n    startDate\n    endDate\n    time\n    imageUrl\n    authName\n    isBooking\n    __typename\n  }\n  __typename\n}"
        }
    ]

    # 명소
    theme_100, isSuccess_theme_100 = await collect_data("100")
    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 80 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    # 맛집,카페
    theme_90, isSuccess_theme_90 = await collect_data("90")
    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 85 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    # 취미생활
    theme_50, isSuccess_theme_50 = await collect_data("50")
    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 90 - current_progress
    progress_bar.update(difference)

    # 놀거리
    theme_30, isSuccess_theme_30 = await collect_data("30")
    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 95 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    # 아이와함께
    theme_60, isSuccess_theme_60 = await collect_data("60")
    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 100 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    return list(dict.fromkeys(theme_100+theme_90+theme_50+theme_30+theme_60)), isSuccess_theme_100 & isSuccess_theme_90 & isSuccess_theme_50 & isSuccess_theme_30 & isSuccess_theme_60


async def get_place_answer(place_url, cnt, interval, pattern):
    '''
    네이버 place 에서 패턴에 맞는 문자를 찾는 함수
    place_url : 가게 url
    pattern : 검색할 패턴
    '''
    global dataInfo, proxyInfo

    placeID = extract_dynamic_number_from_url(place_url)
    match = re.search(r'/(\w+)/\d+', place_url)
    if match:
        businessType = match.group(1)
    else:
        msg = f'{place_url} 의 businessType 을 확인할 수 없습니다'
        writelog(msg, False)
        return None

    title = find_key_by_url(place_url)
    if title:
        primary_key = title.split('-')[-1]
    else:
        primary_key = '삭제된 정보'

    async def collect_data(client, isFirst=True):
        nonlocal place_url, placeID, businessType, cnt, interval, primary_key
        answer_list = []
        isSuccess = False
        businessID = '0'
        try:
            while True:
                try:
                    response = await client.get(f'{place_url.replace("home", "information")}')
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_place_answer : {place_url}\n{msg}', False))
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_place_answer : {response.status_code} error', False))
                        break
                    html = response.text
                    soup = bs(html, 'html.parser')
                    info_content = soup.find('div', class_='AX_W3 _6sPQ')
                    if info_content:
                        answer_list.append(info_content.text)
                    else:
                        # 정규 표현식을 사용하여 필요한 문자열 추출
                        match = re.search(
                            r'"description[^\)]+\)":\s*"([^"]+)"', html)
                        if match:
                            extracted_text = match.group(1)
                            answer_list.append(extracted_text.replace(
                                '\\n', ' ').replace('\n', ' '))
                    # 주차정보
                    parking_content = soup.find('span', class_='zPfVt')
                    if parking_content:
                        answer_list.append(
                            "주차가능 : " + parking_content.text.replace('\n', ' '))
                    else:
                        # 정규 표현식을 사용하여 필요한 문자열 추출
                        match = re.search(
                            r'"parkingInfo":{"__typename":"InformationParking","description":"([^"]+)"', html)
                        if match:
                            extracted_text = match.group(1)
                            answer_list.append(
                                "주차가능 : " + extracted_text.replace('\n', ' '))

                    # 키워드
                    keyword_content = soup.find_all('span', class_='RLvZP')
                    keyword_list = list()
                    for keyword in keyword_content:
                        keyword_list.append(keyword.text)
                    else:
                        # 정규 표현식을 사용하여 필요한 문자열 추출
                        match = re.search(
                            r'"keywordList":\[([^\]]+)\]', html)
                        if match:
                            extracted_text = match.group(1)
                            keyword_list = extracted_text.replace(
                                '"', '').split(',')
                    if bool(keyword_list):
                        answer_list.append(' '.join(keyword_list))

                    # businessID 확인
                    if businessType == 'hairshop':
                        # 정규 표현식을 사용하여 필요한 문자열 추출
                        match = re.search(
                            r'Stylist:[^"]+.*?"businessId":(\d+)', html)
                    else:
                        # 정규 표현식을 사용하여 필요한 문자열 추출
                        match = re.search(
                            r'BookingItem:[^"]+.*?"businessId":(\d+)', html)
                    if match:
                        businessID = match.group(1)
                    else:
                        businessID = "null"
                    isSuccess = True
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    return None, isSuccess

            with tqdm(total=100, desc=primary_key, leave=False, dynamic_ncols=True) as progress_bar:
                # base 맟 지도
                base_info_list, cidList, naverBlog, base_coordinate, base_status = await get_place_location(
                    place_url, placeID, businessType, client)
                answer_list.extend(base_info_list)
                isSuccess = isSuccess and base_status
                if not base_status:
                    # base 정보를 얻지 못하면 종료
                    return list(dict.fromkeys(answer_list)), isSuccess

                # # 스타일리스트
                # if businessType == 'hairshop':
                #     style_list, style_status = await get_place_stylelist(place_url, businessID, businessType, session)
                #     answer_list.extend(style_list)
                #     isSuccess = isSuccess and style_status
                #     if isFirst and not isSuccess:
                #         # 첫번째 시도면 재시도하도록 함수 종료
                #         return answer_list, isSuccess
                #     await asyncio.sleep(interval)

                # 예약정보 (스타일리스트 포함)
                booking_list, booking_status = await get_place_booking(place_url, businessID, businessType, client)
                answer_list.extend(booking_list)
                isSuccess = isSuccess and booking_status
                if isFirst and not isSuccess:
                    # 첫번째 시도면 재시도하도록 함수 종료
                    return answer_list, isSuccess

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 5 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

                # 소식
                feed_list, feed_status = await get_place_feed(place_url,
                                                              placeID, naverBlog, cnt, interval, client, progress_bar)
                answer_list.extend(feed_list)
                isSuccess = isSuccess and feed_status
                if isFirst and not isSuccess:
                    # 첫번째 시도면 재시도하도록 함수 종료
                    return answer_list, isSuccess

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 25 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

                # 리뷰
                review_list, review_status = await get_place_review(place_url,
                                                                    placeID, businessID, businessType, cidList, cnt, interval, client, progress_bar)
                answer_list.extend(review_list)
                isSuccess = isSuccess and review_status
                if isFirst and not isSuccess:
                    # 첫번째 시도면 재시도하도록 함수 종료
                    return answer_list, isSuccess

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 50 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

                # 블로그
                blog_list, blog_status = await get_place_blog(place_url, placeID,
                                                              businessType, cnt, interval, client, progress_bar)
                answer_list.extend(blog_list)
                isSuccess = isSuccess and blog_status
                if isFirst and not isSuccess:
                    # 첫번째 시도면 재시도하도록 함수 종료
                    return answer_list, isSuccess

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 75 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

                # 주변
                arround_list, arround_status = await get_place_arround(place_url, placeID, base_coordinate,
                                                                       cnt, interval, client, progress_bar)
                answer_list.extend(arround_list)
                isSuccess = isSuccess and arround_status
                if isFirst and not isSuccess:
                    # 첫번째 시도면 재시도하도록 함수 종료
                    return answer_list, isSuccess

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 100 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

        except Exception as e:
            msg = f'{traceback.format_exc()}'
            asyncio.create_task(writelog(msg, False))
            return None, False

        return list(dict.fromkeys(answer_list)), isSuccess

    # fetch_with_playwright를 사용하여 쿠키 가져오기
    asyncio.create_task(writelog(f'get_place_answer: Fetching cookies with Playwright for {place_url}', False))
    html_content, status_code, browser_cookies, playwright_user_agent = await fetch_with_playwright(place_url)

    # Playwright에서 쿠키를 2개 이상 정상적으로 가져왔는지 확인
    use_playwright_cookies = len(browser_cookies) >= 2

    if use_playwright_cookies:
        # Playwright 쿠키와 user_agent 사용
        selected_user_agent = playwright_user_agent
        asyncio.create_task(writelog(
            f'get_place_answer: Using Playwright user_agent and {len(browser_cookies)} cookies', False))
    else:
        # ini 설정 사용
        selected_user_agent = dataInfo.User_Agent
        asyncio.create_task(writelog(
            f'get_place_answer: Using ini config user_agent (Playwright cookies: {len(browser_cookies)})', False))

    # BrowserLikeClient 생성 (use_playwright_cookies 플래그로 쿠키 중복 방지)
    client = BrowserLikeClient(
        user_agent=selected_user_agent,
        store_token=dataInfo.store_token,
        store_nnb=dataInfo.store_nnb,
        store_fwb=dataInfo.store_fwb,
        store_buc=dataInfo.store_buc,
        use_playwright_cookies=use_playwright_cookies,
        proxy_config=proxyInfo.url)

    # Playwright에서 가져온 쿠키를 BrowserLikeClient에 설정 (2개 이상일 때만)
    if use_playwright_cookies:
        client.cookie_manager.set_cookies_from_playwright(browser_cookies, place_url)

    # refresh 버퍼에 추가
    async with dataInfo.refresh_buf_lock:
        dataInfo.refresh_buf[place_url] = dict()
        dataInfo.refresh_buf[place_url]['progress'] = 0
        dataInfo.refresh_buf[place_url]['remaining_time'] = "알 수 없음"

    answer_list, collect_status = await collect_data(client, True)
    curLen = len(dataInfo.naverBuf.get(place_url, []))

    # 데이터를 다시 수집해야 하는 경우
    if not collect_status:
        await asyncio.sleep(interval)
        answer_list, collect_status = await collect_data(client, False)

    await client.close()

    # 수집이 완료되면 리프레시 버퍼에서 제거
    async with dataInfo.refresh_buf_lock:
        del dataInfo.refresh_buf[place_url]

    # 버퍼에 저장
    if bool(answer_list) and collect_status:
        async with dataInfo.naverBuf_lock:
            if curLen > 0:
                # 중복되지 않은 새 값 찾기
                new_unique_items = [
                    item for item in answer_list if item not in dataInfo.naverBuf[place_url]]

                # 기존 정답 중 새로 찾은 값에 포함되는 값 찾기
                matching_items = [
                    item for item in dataInfo.naverBuf[place_url]
                    if item is None or any((item in answer or item.replace('\n', ' ') in answer.replace('\n', ' ')) and item != answer for answer in answer_list if answer is not None)
                ]

                # matching_items를 dataInfo.naverBuf[place_url]에서 제거
                dataInfo.naverBuf[place_url] = [
                    item for item in dataInfo.naverBuf[place_url] if item not in matching_items
                ]

                # 새로운 값 리스트 앞에 추가
                combined_list = new_unique_items + \
                    dataInfo.naverBuf[place_url]
                dataInfo.naverBuf[place_url] = combined_list
            else:
                dataInfo.naverBuf[place_url] = answer_list
            await naverBufInfo.save_pickle(dataInfo.naverBuf)
        msg = f'{primary_key} 정보수집 성공: ({curLen} → {len(dataInfo.naverBuf.get(place_url, []))})'
        asyncio.create_task(writelog(msg, False))
    else:
        msg = f'{primary_key} 정보수집 {"없음" if collect_status else "실패"}: ({curLen} → {len(answer_list) if bool(answer_list) else 0}) {"🌑" if collect_status else "🚨"}'
        asyncio.create_task(writelog(msg, False))

    if not pattern:
        return collect_status, f'{curLen} → {len(dataInfo.naverBuf.get(place_url, []))}'

    return find_pattern_in_list(answer_list, pattern) if answer_list else None


async def get_store_review(store_url, productNo, merchantNo, cnt, interval, client, progress_bar: tqdm):
    '''
    지도 가져오기n
    productNo : 상품 ID
    merchantNo : 리뷰 ID
    cnt : 가져올 갯수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    global dataInfo

    async def collect_data(sortType):
        '''
        데이터를 수집하는 함수
        sortType : 정렬방법, REVIEW_RANKING or REVIEW_CREATE_DATE_DESC
        '''
        nonlocal dataDict, client, progress_bar

        dataDict['reviewSearchSortType'] = sortType
        result = []
        isSuccess = False
        review_offset = 0
        current_progress = progress_bar.n
        for i in range(1, cnt + 1):
            dataDict['page'] = i
            should_break = False  # 외부 for 루프를 제어하기 위한 변수
            try_count = 0  # 시도 횟수를 카운트하기 위한 변수
            while try_count < 3:
                try:
                    response = await client.post('https://smartstore.naver.com/i/v1/contents/reviews/query-pages', json_data=dataDict, referer=store_url)
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_store_review : {store_url}\n{msg}', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_store_review : {store_url} : {response.status_code} error', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_store_review : {response.status_code}', False))
                        isSuccess = True
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code != 200:
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    result_json = response.json()
                    review_offset += len(result_json['contents'])
                    result += extract_values(result_json,
                                             ['createDate', 'reviewContent'])
                    if result_json['totalElements'] == review_offset:
                        # 모든 리뷰를 가지고 왔을 경우
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                    break
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    try_count += 1
                    continue
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    try_count += 1
                    asyncio.create_task(writelog(msg, False))
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break

            # 진행률 계산
            target_progress = current_progress + (i*50) / cnt
            difference = target_progress - progress_bar.n
            difference_int = int(difference)
            # 진행률 막대를 목표 진행률로 업데이트합니다.
            progress_bar.update(difference_int)
            remaining_seconds = progress_bar._time() - progress_bar.start_t
            if progress_bar.n == 0:
                remaining_time = "알 수 없음"
            else:
                remaining_seconds = remaining_seconds * \
                    (progress_bar.total - progress_bar.n) / progress_bar.n
                remaining_time = format_time(remaining_seconds)
            dataInfo.refresh_buf[store_url]['progress'] = progress_bar.n
            dataInfo.refresh_buf[store_url]['remaining_time'] = remaining_time
            if should_break:  # for 루프를 탈출해야 하는 경우
                break
            await asyncio.sleep(interval)
        else:
            # 수집 횟수를 모두 채우면 성공
            isSuccess = True
        return list(dict.fromkeys(result)), isSuccess

    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'TE': 'trailers',
        'User-Agent': dataInfo.User_Agent
    }
    # smartstore dict
    dataDict = {
        "checkoutMerchantNo": merchantNo,
        "originProductNo": productNo,
        "page": 0,
        "pageSize": 20
    }

    # 추천순
    result_ranking, isSuccess_ranking = await collect_data("REVIEW_RANKING")

    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 50 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[store_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[store_url]['remaining_time'] = remaining_time

    # 최신순
    result_recent, isSuccess_recent = await collect_data("REVIEW_CREATE_DATE_DESC")

    return list(dict.fromkeys(result_ranking+result_recent)), isSuccess_ranking & isSuccess_recent


async def get_brand_review(store_url, productNo, merchantNo, cnt, interval, client, progress_bar: tqdm):
    '''
    지도 가져오기
    productNo : 상품 ID
    merchantNo : 리뷰 ID
    cnt : 가져올 걋수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    global dataInfo

    async def collect_data(sortType):
        '''
        데이터를 수집하는 함수
        sortType : 정렬방법, REVIEW_RANKING or REVIEW_CREATE_DATE_DESC
        '''
        nonlocal dataDict, client, progress_bar

        dataDict['reviewSearchSortType'] = sortType
        result = []
        isSuccess = False
        review_offset = 0
        current_progress = progress_bar.n
        for i in range(1, cnt + 1):
            dataDict['page'] = i
            should_break = False  # 외부 for 루프를 제어하기 위한 변수
            try_count = 0  # 시도 횟수를 카운트하기 위한 변수
            while try_count < 3:
                try:
                    response = await client.post('https://brand.naver.com/n/v1/contents/reviews/query-pages', json_data=dataDict, referer=store_url)
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_brand_review : {store_url}\n{msg}', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_brand_review : {store_url} : {response.status_code} error', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_brand_review : {response.status_code}', False))
                        isSuccess = True
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code != 200:
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    result_json = response.json()
                    # result += extract_values(result_json,['reviewContent', 'commentContent'])
                    review_offset += len(result_json['contents'])
                    result += extract_values(result_json,
                                             ['createDate', 'reviewContent'])
                    if result_json['totalElements'] == review_offset:
                        # 모든 리뷰를 가지고 왔을 경우
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                    break  # while 루프 탈출
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    try_count += 1
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    try_count += 1
                    asyncio.create_task(writelog(msg, False))
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break

            # 진행률 계산
            target_progress = current_progress + (i*50) / cnt
            difference = target_progress - progress_bar.n
            difference_int = int(difference)
            # 진행률 막대를 목표 진행률로 업데이트합니다.
            progress_bar.update(difference_int)
            remaining_seconds = progress_bar._time() - progress_bar.start_t
            if progress_bar.n == 0:
                remaining_time = "알 수 없음"
            else:
                remaining_seconds = remaining_seconds * \
                    (progress_bar.total - progress_bar.n) / progress_bar.n
                remaining_time = format_time(remaining_seconds)
            dataInfo.refresh_buf[store_url]['progress'] = progress_bar.n
            dataInfo.refresh_buf[store_url]['remaining_time'] = remaining_time
            if should_break:  # for 루프를 탈출해야 하는 경우
                break
            await asyncio.sleep(interval)
        else:
            # 수집 횟수를 모두 채우면 성공
            isSuccess = True

        return list(dict.fromkeys(result)), isSuccess

    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'TE': 'trailers',
        'User-Agent': dataInfo.User_Agent
    }

    # smartstore dict
    dataDict = {
        "checkoutMerchantNo": int(merchantNo),
        "originProductNo": int(productNo),
        "page": 0,
        "pageSize": 20
    }

    # 추천순
    result_ranking, isSuccess_ranking = await collect_data("REVIEW_RANKING")

    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 50 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[store_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[store_url]['remaining_time'] = remaining_time

    # 최신순
    result_recent, isSuccess_recent = await collect_data("REVIEW_CREATE_DATE_DESC")

    return list(dict.fromkeys(result_ranking+result_recent)), isSuccess_ranking & isSuccess_recent


async def get_kakao_place_review(place_url, placeID, commentID, cnt, interval, client, progress_bar: tqdm):
    '''
    리뷰 가져오기
    place_url : place 주소
    placeID : 가게 ID
    commentID : 마지막으로 가져온 commment ID
    cnt : 가져올 페이지 수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    global dataInfo, proxyInfo

    async def collect_data(reviewSort=None):
        '''
        데이터를 수집하는 함수
        reviewSort : 정렬방법, 최신순은 recent
        '''
        nonlocal commentID, client, progress_bar

        result = []
        review_offset = 0
        isSuccess = False
        current_progress = progress_bar.n
        # 리뷰를 가져옴
        for i in range(1, cnt + 1):
            should_break = False  # 외부 for 루프를 제어하기 위한 변수
            try_count = 0  # 시도 횟수를 카운트하기 위한 변수
            while try_count < 3:
                try:
                    # debug code
                    response = await client.get(f'https://place.map.kakao.com/commentlist/v/{placeID}/{commentID}')
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_place_review : {place_url}\n{msg}', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_place_review : {response.status_code} error', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_place_review : {response.status_code}', False))
                        isSuccess = True
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code != 200:
                        try_count += 1
                        # 300ms 대기
                        await asyncio.sleep(dataInfo.errInterval*try_count**2)
                        continue
                    result_json = response.json()
                    if not bool(result_json['comment']['list']):
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                        break
                    review_offset += len(result_json['comment']['list'])
                    result += extract_values(result_json['comment']['list'], [
                                             'username', 'date', 'contents'])
                    if not result_json['comment'].get('hasNext', False):
                        # 모든 리뷰를 가지고 왔을 경우
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                        break
                    # 다음 페이지를 가져오기 위한 마지막 댓글ID
                    commentID = result_json['comment']['list'][-1]['commentid']
                    break  # while 루프 탈출
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    try_count += 1
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    try_count += 1
                    asyncio.create_task(writelog(msg, False))
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break  # while 루프 탈출

            # 진행률 계산
            target_progress = current_progress + (i+1)*50 / cnt
            difference = target_progress - progress_bar.n
            difference_int = int(difference)
            # 진행률 막대를 목표 진행률로 업데이트합니다.
            progress_bar.update(difference_int)
            remaining_seconds = progress_bar._time() - progress_bar.start_t
            if progress_bar.n == 0:
                remaining_time = "알 수 없음"
            else:
                remaining_seconds = remaining_seconds * \
                    (progress_bar.total - progress_bar.n) / progress_bar.n
                remaining_time = format_time(remaining_seconds)
            dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
            dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

            if should_break:  # for 루프를 탈출해야 하는 경우
                break
            await asyncio.sleep(interval)
        else:
            # 수집 횟수를 모두 채우면 성공
            isSuccess = True

        return list(dict.fromkeys(result)), isSuccess

    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }

    result_comment, isSuccess = await collect_data()

    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 50 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    return result_comment, isSuccess


async def get_kakao_blog_review(place_url, placeID, moreID, cnt, interval, client, progress_bar: tqdm):
    '''
    블로그 리뷰 가져오기
    place_url : place 주소
    placeID : 가게 ID
    moreID : 마지막으로 가져온 리뷰 ID
    cnt : 가져올 페이지 수
    interval : 다음페이지 조회 간격
    client : httpx
    progress_bar : tqdm 진행바
    '''
    global dataInfo, proxyInfo

    async def collect_data(reviewSort=None):
        '''
        데이터를 수집하는 함수
        reviewSort : 정렬방법, 최신순은 recent
        '''
        nonlocal moreID, client, progress_bar

        result = []
        review_offset = 0
        isSuccess = False
        current_progress = progress_bar.n
        # 리뷰를 가져옴
        for i in range(1, cnt + 1):
            should_break = False  # 외부 for 루프를 제어하기 위한 변수
            try_count = 0  # 시도 횟수를 카운트하기 위한 변수
            while try_count < 3:
                try:
                    # debug code
                    response = await client.get(f'https://place.map.kakao.com/blogrvwlist/v/{placeID}/{moreID}')
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_place_review : {place_url}\n{msg}', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_place_review : {response.status_code} error', False))
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_place_review : {response.status_code}', False))
                        isSuccess = True
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        break
                    elif response.status_code != 200:
                        try_count += 1
                        # 300ms 대기
                        await asyncio.sleep(dataInfo.errInterval*try_count**2)
                        continue
                    result_json = response.json()
                    if not bool(result_json['blogReview']['list']):
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                        break
                    review_offset += len(result_json['blogReview']['list'])
                    result += extract_values(result_json['blogReview']['list'], [
                                             'title', 'contents', 'blogname', 'date'])
                    if not result_json['blogReview'].get('moreId', False):
                        # 모든 리뷰를 가지고 왔을 경우
                        should_break = True  # for 루프를 탈출해야 함을 표시
                        isSuccess = True
                        break
                    # 다음 페이지를 가져오기 위한 마지막 댓글ID
                    moreID = result_json['blogReview']['moreId']
                    break  # while 루프 탈출
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    try_count += 1
                    await asyncio.sleep(dataInfo.errInterval*try_count**2)
                    continue
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    try_count += 1
                    asyncio.create_task(writelog(msg, False))
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    should_break = True  # for 루프를 탈출해야 함을 표시
                    break  # while 루프 탈출

            # 진행률 계산
            target_progress = current_progress + (i+1)*100 / cnt
            difference = target_progress - progress_bar.n
            difference_int = int(difference)
            # 진행률 막대를 목표 진행률로 업데이트합니다.
            progress_bar.update(difference_int)
            remaining_seconds = progress_bar._time() - progress_bar.start_t
            if progress_bar.n == 0:
                remaining_time = "알 수 없음"
            else:
                remaining_seconds = remaining_seconds * \
                    (progress_bar.total - progress_bar.n) / progress_bar.n
                remaining_time = format_time(remaining_seconds)
            dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
            dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

            if should_break:  # for 루프를 탈출해야 하는 경우
                break
            await asyncio.sleep(interval)
        else:
            # 수집 횟수를 모두 채우면 성공
            isSuccess = True

        return list(dict.fromkeys(result)), isSuccess

    header = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Cookie': 'ba.uuid=0',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': dataInfo.User_Agent
    }

    result_review, isSuccess = await collect_data()

    # progress_bar 업데이트
    current_progress = progress_bar.n
    difference = 100 - current_progress
    progress_bar.update(difference)
    remaining_seconds = progress_bar._time() - progress_bar.start_t
    if progress_bar.n == 0:
        remaining_time = "알 수 없음"
    else:
        remaining_seconds = remaining_seconds * \
            (progress_bar.total - progress_bar.n) / progress_bar.n
        remaining_time = format_time(remaining_seconds)
    dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
    dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

    return result_review, isSuccess


async def get_kakao_place_answer(place_url, cnt, interval, pattern):
    '''
    카카오맵 place 에서 패턴에 맞는 문자를 찾는 함수
    place_url : 가게 url
    pattern : 검색할 패턴
    '''
    global dataInfo, proxyInfo

    placeID = extract_dynamic_number_from_url(place_url)
    title = find_key_by_url(place_url)
    if title:
        primary_key = title.split('-')[-1]
    else:
        primary_key = '삭제된 정보'

    async def collect_data(client, isFirst=True):
        nonlocal place_url, placeID, cnt, interval, primary_key
        answer_list = []
        review_offset = 0
        isSuccess = False
        try:
            while True:
                try:
                    response = await client.get(f'https://place-api.map.kakao.com/places/panel3/{placeID}')
                    if response.status_code == 429:
                        # 429 Too Many Requests
                        msg = response.text
                        asyncio.create_task(
                            writelog(f'get_kakao_place_answer : {place_url}\n{msg}', False))
                        break
                    elif 500 <= response.status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_kakao_place_answer : {response.status_code} error', False))
                        break
                    elif response.status_code == 204:
                        # 204 No Content
                        asyncio.create_task(
                            writelog(f'get_kakao_place_answer : {response.status_code}', False))
                        break
                    result_json = response.json()
                    break
                except json.decoder.JSONDecodeError:
                    msg = response.text
                    asyncio.create_task(writelog(msg, False))
                    return None, isSuccess
                except TypeError:
                    msg = response.text
                    msg += f'{traceback.format_exc()}'
                    return None, isSuccess
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    return None, isSuccess

            with tqdm(total=100, desc=primary_key, leave=False, dynamic_ncols=True) as progress_bar:
                # basicInfo
                # 메뉴
                if 'menuList' in result_json['menuInfo']:
                    answer_list += extract_values(
                        result_json['menuInfo']['menuList'], ['menu', 'price'])
                # 전화번호
                if result_json['basicInfo'].get('phonenum', None):
                    answer_list.append(
                        '📞 '+result_json['basicInfo']['phonenum'] + ' 대표번호')
                isSuccess = True

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 5 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

                # comment
                if 'comment' in result_json:
                    answer_list += extract_values(result_json['comment']['list'], [
                                                  'username', 'date', 'contents'])
                    if result_json['comment'].get('hasNext', False):
                        review_list, review_status = await get_kakao_place_review(place_url, placeID, result_json['comment']['list'][-1]['commentid'], cnt, interval, client, progress_bar)
                answer_list.extend(review_list)
                isSuccess = isSuccess and review_status
                if isFirst and not isSuccess:
                    # 첫번째 시도면 재시도하도록 함수 종료
                    return answer_list, isSuccess

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 50 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

                # blogReview
                if 'blogReview' in result_json:
                    answer_list += extract_values(result_json['blogReview']['list'], [
                                                  'title', 'contents', 'blogname', 'date'])
                    if result_json['blogReview'].get('moreId', False):
                        blog_list, blog_status = await get_kakao_blog_review(place_url, placeID, result_json['blogReview']['moreId'], cnt, interval, client, progress_bar)
                answer_list.extend(blog_list)
                isSuccess = isSuccess and blog_status
                if isFirst and not isSuccess:
                    # 첫번째 시도면 재시도하도록 함수 종료
                    return answer_list, isSuccess

                # progress_bar 업데이트
                current_progress = progress_bar.n
                difference = 100 - current_progress
                progress_bar.update(difference)
                remaining_seconds = progress_bar._time() - progress_bar.start_t
                if progress_bar.n == 0:
                    remaining_time = "알 수 없음"
                else:
                    remaining_seconds = remaining_seconds * \
                        (progress_bar.total - progress_bar.n) / progress_bar.n
                    remaining_time = format_time(remaining_seconds)
                dataInfo.refresh_buf[place_url]['progress'] = progress_bar.n
                dataInfo.refresh_buf[place_url]['remaining_time'] = remaining_time

        except Exception as e:
            msg = f'{traceback.format_exc()}'
            asyncio.create_task(writelog(msg, False))
            return None, False

        return list(dict.fromkeys(answer_list)), isSuccess

    # fetch_with_playwright를 사용하여 쿠키 가져오기
    asyncio.create_task(writelog(f'get_kakao_place_answer: Fetching cookies with Playwright for {place_url}', False))
    html_content, status_code, browser_cookies, playwright_user_agent = await fetch_with_playwright(place_url)

    # Playwright에서 쿠키를 2개 이상 정상적으로 가져왔는지 확인
    use_playwright_cookies = len(browser_cookies) >= 2

    if use_playwright_cookies:
        # Playwright 쿠키와 user_agent 사용
        selected_user_agent = playwright_user_agent
        asyncio.create_task(writelog(
            f'get_kakao_place_answer: Using Playwright user_agent and {len(browser_cookies)} cookies', False))
    else:
        # ini 설정 사용
        selected_user_agent = dataInfo.User_Agent
        asyncio.create_task(writelog(
            f'get_kakao_place_answer: Using ini config user_agent (Playwright cookies: {len(browser_cookies)})', False))

    # BrowserLikeClient 생성 (use_playwright_cookies 플래그로 쿠키 중복 방지)
    client = BrowserLikeClient(
        user_agent=selected_user_agent,
        store_token=dataInfo.store_token,
        store_nnb=dataInfo.store_nnb,
        store_fwb=dataInfo.store_fwb,
        store_buc=dataInfo.store_buc,
        use_playwright_cookies=use_playwright_cookies,
        proxy_config=proxyInfo.url)

    # Playwright에서 가져온 쿠키를 BrowserLikeClient에 설정 (2개 이상일 때만)
    if use_playwright_cookies:
        client.cookie_manager.set_cookies_from_playwright(browser_cookies, place_url)

    # refresh 버퍼에 추가
    async with dataInfo.refresh_buf_lock:
        dataInfo.refresh_buf[place_url] = dict()
        dataInfo.refresh_buf[place_url]['progress'] = 0
        dataInfo.refresh_buf[place_url]['remaining_time'] = '알 수 없음'

    answer_list, collect_status = await collect_data(client, True)
    curLen = len(dataInfo.naverBuf.get(place_url, []))

    # 데이터를 다시 수집해야 하는 경우
    if not collect_status:
        await asyncio.sleep(interval)
        answer_list, collect_status = await collect_data(client, False)

    # 수집이 완료되면 리프레시 버퍼에서 제거
    async with dataInfo.refresh_buf_lock:
        del dataInfo.refresh_buf[place_url]

    await client.close()

    # 버퍼에 저장
    if bool(answer_list) and collect_status:
        async with dataInfo.naverBuf_lock:
            if curLen > 0:
                # 중복되지 않은 새 값 찾기
                new_unique_items = [
                    item for item in answer_list if item not in dataInfo.naverBuf[place_url]]

                # 기존 정답 중 새로 찾은 값에 포함되는 값 찾기
                matching_items = [
                    item for item in dataInfo.naverBuf[place_url]
                    if item is None or any((item in answer or item.replace('\n', ' ') in answer.replace('\n', ' ')) and item != answer for answer in answer_list if answer is not None)
                ]

                # matching_items를 dataInfo.naverBuf[place_url]에서 제거
                dataInfo.naverBuf[place_url] = [
                    item for item in dataInfo.naverBuf[place_url] if item not in matching_items
                ]

                # 새로운 값 리스트 앞에 추가
                combined_list = new_unique_items + \
                    dataInfo.naverBuf[place_url]
                dataInfo.naverBuf[place_url] = combined_list
            else:
                dataInfo.naverBuf[place_url] = answer_list
            await naverBufInfo.save_pickle(dataInfo.naverBuf)
        msg = f'{primary_key} 정보수집 성공: ({curLen} → {len(dataInfo.naverBuf.get(place_url, []))})'
        asyncio.create_task(writelog(msg, False))
    else:
        msg = f'{primary_key} 정보수집 {"없음" if collect_status else "실패"}: ({curLen} → {len(answer_list) if bool(answer_list) else 0}) {"🌑" if collect_status else "🚨"}'
        asyncio.create_task(writelog(msg, False))

    if not pattern:
        return collect_status, f'{curLen} → {len(dataInfo.naverBuf.get(place_url, []))}'

    return find_pattern_in_list(answer_list, pattern) if answer_list else None


def extract_key_values_from_script(html_content):
    '''
    naver store 에서 productNo와 naverPaySellerNo 를 확인하는 함수
    '''
    soup = bs(html_content, 'html.parser')
    script_texts = soup.find_all('script')
    results = {}

    # 정규식으로 키와 값을 찾기
    patterns = {
        "checkoutMerchantNo": r'"payReferenceKey"\s*:\s*"(\d+)"',
        "originProductNo": r'"productNo"\s*:\s*(?:")?(\d+)"?,"salePrice"'
    }

    # 스크립트 태그들에서 모든 텍스트를 검사
    try:
        for script in script_texts:
            for key, pattern in patterns.items():
                match = re.search(pattern, script.text)
                if match:
                    results[key] = match.group(1)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        writelog(msg, False)
    return results


async def fetch_with_playwright(url: str) -> Tuple[str, int, List[Dict], str]:
    """
    Playwright를 사용하여 URL을 가져옵니다. 네이버의 봇 감지를 우회하기 위한 다양한 기법을 사용합니다.

    실제 사용자처럼 행동하여 자연스럽게 쿠키를 획득합니다.

    Args:
        url: 가져올 URL

    Returns:
        Tuple[str, int, List[Dict], str]: (HTML 콘텐츠, HTTP 상태 코드, 브라우저 쿠키 리스트, 사용한 User-Agent)
    """
    try:
        async with async_playwright() as p:
            # 실제 Chrome/Edge 바이너리 사용 (Chromium은 봇 탐지됨)
            browser = None

            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]

            # Edge User-Agent (브라우저와 일치)
            edge_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'

            # Edge만 사용 (Windows 기본 설치)
            try:
                browser = await p.chromium.launch(
                    channel='msedge',
                    headless=True,
                    args=launch_args
                )
                asyncio.create_task(writelog(f'fetch_with_playwright: Using Edge (channel=msedge)', False))
            except Exception as edge_error:
                # Edge 없으면 조용히 실패 (Chromium은 봇 탐지되므로 사용 안함)
                msg = f'fetch_with_playwright: Edge not found. {str(edge_error)[:150]}'
                asyncio.create_task(writelog(msg, False))
                return "", 0, [], edge_ua

            # 컨텍스트 생성
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=edge_ua,
                locale='ko-KR',
                timezone_id='Asia/Seoul',
                permissions=[],
                ignore_https_errors=True,  # SSL 인증서 오류 무시
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
            )

            # 페이지 생성 (실제 브라우저처럼 새로운 세션으로 시작)
            page = await context.new_page()

            # WebDriver 속성 제거 및 다양한 봇 감지 우회 (강화된 버전)
            await page.add_init_script("""
                // WebDriver 속성 완전 제거
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });

                delete Object.getPrototypeOf(navigator).webdriver;

                // Chrome 객체 추가 (더 완전하게)
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {
                        isInstalled: false,
                        InstallState: {
                            DISABLED: 'disabled',
                            INSTALLED: 'installed',
                            NOT_INSTALLED: 'not_installed'
                        },
                        RunningState: {
                            CANNOT_RUN: 'cannot_run',
                            READY_TO_RUN: 'ready_to_run',
                            RUNNING: 'running'
                        }
                    }
                };

                // Permissions 덮어쓰기
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Plugins 설정 (더 현실적으로)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const plugins = [
                            {
                                0: {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format'},
                                description: 'Portable Document Format',
                                filename: 'internal-pdf-viewer',
                                length: 1,
                                name: 'Chrome PDF Plugin'
                            },
                            {
                                0: {type: 'application/pdf', suffixes: 'pdf', description: ''},
                                description: '',
                                filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                                length: 1,
                                name: 'Chrome PDF Viewer'
                            },
                            {
                                0: {type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable'},
                                1: {type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable'},
                                description: '',
                                filename: 'internal-nacl-plugin',
                                length: 2,
                                name: 'Native Client'
                            }
                        ];
                        plugins.length = 3;
                        return plugins;
                    }
                });

                // Languages 설정
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ko-KR', 'ko', 'en-US', 'en']
                });

                // Platform 설정
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });

                // Vendor 설정
                Object.defineProperty(navigator, 'vendor', {
                    get: () => 'Google Inc.'
                });

                // Hardware Concurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });

                // Device Memory
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });

                // Connection
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false,
                        onchange: null,
                        ontypechange: null
                    })
                });

                // maxTouchPoints 설정
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 0
                });

                // Battery API 숨기기
                if ('getBattery' in navigator) {
                    navigator.getBattery = undefined;
                }

                // WebGL Vendor/Renderer 정보 수정
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter.apply(this, [parameter]);
                };

                // Canvas fingerprinting 방지
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    if (type === 'image/png' && this.width === 16 && this.height === 16) {
                        return originalToDataURL.apply(this, arguments);
                    }
                    return originalToDataURL.apply(this, arguments);
                };

                // Notification.permission 설정
                if ('Notification' in window) {
                    Notification.permission = 'default';
                }
            """)

            # 먼저 네이버 메인 페이지 방문 (정상 사용자 행동 모방, 쿠키 획득)
            try:
                await page.goto('https://www.naver.com', wait_until='load', timeout=30000)
                # 충분한 대기 시간을 주어 JavaScript가 쿠키를 설정하도록 함
                await page.wait_for_timeout(5000)  # 5초 대기 (쿠키 설정 완료 대기)

                # 현실적인 사용자 행동 시뮬레이션
                try:
                    # 페이지 스크롤 (사용자처럼 보이기 위해)
                    await page.evaluate('window.scrollTo(0, 500)')
                    await page.wait_for_timeout(500)
                    await page.evaluate('window.scrollTo(0, 1000)')
                    await page.wait_for_timeout(500)
                    await page.evaluate('window.scrollTo(0, 0)')
                    await page.wait_for_timeout(1000)
                except:
                    pass  # 스크롤 실패해도 계속 진행
            except Exception as e:
                # 메인 페이지 로드 실패해도 계속 진행 (단, CancelledError는 재발생)
                if isinstance(e, asyncio.CancelledError):
                    raise
                asyncio.create_task(writelog(
                    f'fetch_with_playwright: Naver main page load failed: {str(e)}', False))

            # 페이지 로드 (타임아웃 60초) with Referer 헤더
            try:
                response = await page.goto(url, wait_until='load', timeout=60000, referer='https://www.naver.com/')
                status_code = response.status if response else 0
            except Exception as e:
                # 페이지 로드 실패 (타임아웃, 네트워크 오류 등)
                asyncio.create_task(
                    writelog(f'fetch_with_playwright: Failed to load {url}: {str(e)}', False))
                status_code = 0
                html_content = ""
                browser_cookies = []

                try:
                    await browser.close()
                except:
                    pass  # 브라우저가 이미 닫혔을 수 있음

                return html_content, status_code, browser_cookies

            html_content = ""
            browser_cookies = []

            try:
                if status_code == 200:
                    # 추가 대기 (동적 콘텐츠 및 쿠키 설정 완료 대기)
                    await page.wait_for_timeout(10000)  # 10초 대기 (매우 긴 대기)

                    # 현실적인 사용자 행동 시뮬레이션 (타겟 페이지에서도)
                    try:
                        await page.evaluate('window.scrollTo(0, 300)')
                        await page.wait_for_timeout(1200)
                        await page.evaluate('window.scrollTo(0, 600)')
                        await page.wait_for_timeout(1200)
                        await page.evaluate('window.scrollTo(0, 900)')
                        await page.wait_for_timeout(1200)

                        # 상품 이미지 클릭 시도 (실제 상호작용)
                        try:
                            await page.click('img', timeout=2000)
                            await page.wait_for_timeout(500)
                        except:
                            pass
                    except:
                        pass

                    # HTML 콘텐츠 가져오기
                    html_content = await page.content()
                elif status_code == 429:
                    # 429 Too Many Requests - ini 설정을 사용한 BrowserLikeClient로 재시도
                    await page.wait_for_timeout(5000)  # 5초 대기
                    html_content = await page.content()

                    # 브라우저 종료
                    try:
                        await browser.close()
                    except:
                        pass

                    # BrowserLikeClient로 재시도
                    asyncio.create_task(writelog(
                        f'fetch_with_playwright: 429 error detected, retrying with BrowserLikeClient using ini config', False))

                    global dataInfo, proxyInfo
                    client = BrowserLikeClient(
                        user_agent=dataInfo.User_Agent,
                        store_token=dataInfo.store_token,
                        store_nnb=dataInfo.store_nnb,
                        store_fwb=dataInfo.store_fwb,
                        store_buc=dataInfo.store_buc,
                        proxy_config=proxyInfo.url)

                    try:
                        response = await client.get(url)
                        if response.status_code == 200:
                            html_content = response.text
                            status_code = response.status_code
                            # BrowserLikeClient의 쿠키를 Playwright 형식으로 변환
                            browser_cookies = client.cookie_manager.get_cookies_for_playwright(url)
                            asyncio.create_task(writelog(
                                f'fetch_with_playwright: BrowserLikeClient retry successful', False))
                        else:
                            asyncio.create_task(writelog(
                                f'fetch_with_playwright: BrowserLikeClient retry failed with status {response.status_code}', False))
                    except Exception as e:
                        asyncio.create_task(writelog(
                            f'fetch_with_playwright: BrowserLikeClient retry error: {str(e)}', False))
                    finally:
                        await client.close()

                    return html_content, status_code, browser_cookies, dataInfo.User_Agent

                elif status_code:
                    # 상태 코드가 있지만 200이 아닌 경우 (403 등)
                    await page.wait_for_timeout(5000)  # 5초 대기
                    html_content = await page.content()
                else:
                    html_content = ""

                # 브라우저에서 쿠키 가져오기 (API 요청에 사용하기 위해)
                # context.cookies()는 파라미터 없이 호출하면 모든 도메인의 쿠키를 반환함
                browser_cookies = await context.cookies()

                # 디버깅: 쿠키 개수와 이름 로그
                cookie_names = [c['name'] for c in browser_cookies]
                cookie_domains = list(set([c.get('domain', 'unknown') for c in browser_cookies]))
                asyncio.create_task(writelog(
                    f'fetch_with_playwright: Retrieved {len(browser_cookies)} cookies from domains {cookie_domains}: {cookie_names}', False))
            except Exception as e:
                # 브라우저가 크래시되었거나 페이지가 닫힌 경우
                asyncio.create_task(writelog(
                    f'fetch_with_playwright: Browser error while processing {url}: {str(e)}', False))

            # 브라우저 종료
            try:
                await browser.close()
            except:
                pass  # 브라우저가 이미 닫혔을 수 있음

            return html_content, status_code, browser_cookies, edge_ua

    except Exception as e:
        msg = f'fetch_with_playwright error: {str(e)}\n{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
        # 실패 시에도 Edge UA 반환
        edge_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'
        return "", 0, [], edge_ua


async def get_store_answer(store_url, cnt, interval, pattern):
    '''
    네이버 place 에서 패턴에 맞는 문자를 찾는 함수
    store_url : 판매 url
    cnt : 정보를 수집할 갯수
    interval : 요청 interval
    pattern : 검색할 패턴
    '''
    global dataInfo, proxyInfo, scriptInfo

    title = find_key_by_url(store_url)
    if title:
        primary_key = title.split('-')[-1]
    else:
        primary_key = '삭제된 정보'

    async def collect_data(client):
        nonlocal primary_key

        answer_list = []
        isSuccess = False
        try_count = 0  # 시도 횟수를 카운트하기 위한 변수
        token_updated = False  # 토큰 업데이트 플래그
        with tqdm(total=100, desc=primary_key, leave=False, dynamic_ncols=True) as progress_bar:
            while try_count < 3:
                try:
                    # Playwright를 사용하여 페이지 가져오기
                    # 실제 사용자처럼 행동하여 자연스럽게 쿠키를 획득
                    html, status_code, browser_cookies, playwright_ua = await fetch_with_playwright(store_url)

                    # Playwright에서 사용한 User-Agent를 httpx 클라이언트에도 적용 (브라우저-UA 일치)
                    client.update_user_agent(playwright_ua)
                    asyncio.create_task(
                        writelog(f'Updated client User-Agent to match Playwright: {playwright_ua}', False))

                    # Playwright에서 얻은 쿠키를 httpx 클라이언트에 적용 (API 요청 시 사용)
                    if browser_cookies:
                        client.cookie_manager.set_cookies_from_playwright(
                            browser_cookies, store_url)
                        asyncio.create_task(
                            writelog(f'Applied {len(browser_cookies)} cookies from Playwright to httpx client for {store_url}', False))

                    if status_code == 429:
                        # 429 Too Many Requests
                        asyncio.create_task(
                            writelog(f'get_store_answer : {store_url} - 429 Too Many Requests', False))
                        break
                    elif status_code == 490 and not token_updated:
                        # Store token 업데이트 필요 (첫 번째 시도만)
                        try:
                            # ini 파일에서 새로운 토큰 읽기
                            config = configparser.ConfigParser()
                            config_file = Path(
                                f'{scriptInfo.dir_path}\\{scriptInfo.script_name}.ini')

                            async with aiofiles.open(config_file, 'r', encoding='utf-8') as f:
                                content = await f.read()
                            config.read_string(content)
                            new_user_agent = literal_eval(
                                config['DATA']['user_agent'])
                            new_store_token = literal_eval(
                                config['DATA']['store_token'])

                            # user agent 또는 토큰이 다르면 업데이트
                            if new_user_agent != client.user_agent or new_store_token != client.store_token:
                                if new_user_agent != client.user_agent:
                                    client.update_user_agent(new_user_agent)
                                    dataInfo.user_agent = new_user_agent  # 전역 상태도 업데이트
                                    token_updated = True
                                    msg = f'User Agent updated due to 490 status code: {store_url}'
                                    asyncio.create_task(writelog(msg, False))
                                if new_store_token != client.store_token:
                                    client.update_store_token(new_store_token)
                                    dataInfo.store_token = new_store_token  # 전역 상태도 업데이트
                                    token_updated = True
                                    msg = f'Store token updated due to 490 status code: {store_url}'
                                    asyncio.create_task(writelog(msg, False))
                                try_count += 1
                                await asyncio.sleep(1)  # 잠시 대기 후 재시도
                                continue
                            else:
                                msg = f'User Agent and token already updated but still getting 490: {store_url}'
                                asyncio.create_task(writelog(msg, False))
                                break

                        except Exception as e:
                            msg = f'get_store_answer : {store_url} : {status_code} error'
                            asyncio.create_task(writelog(msg, False))
                            break
                    elif status_code == 490 and token_updated:
                        # 이미 토큰을 업데이트했지만 여전히 490이면 종료
                        msg = f'Store token already updated but still getting 490: {store_url}'
                        asyncio.create_task(writelog(msg, False))
                        break
                    elif 500 <= status_code < 600:
                        asyncio.create_task(
                            writelog(f'get_store_answer : {store_url} : {status_code} error', False))
                        break
                    elif status_code != 200:
                        asyncio.create_task(
                            writelog(f'get_store_answer : {store_url} : {status_code} status code (expected 200)', False))
                        break
                    # html 변수는 이미 fetch_with_playwright에서 받아옴
                    store_info = extract_key_values_from_script(html)
                    if not bool(store_info):
                        break

                    if 'smartstore' in store_url:
                        answer_list, isSuccess = await get_store_review(store_url,
                                                                        store_info['originProductNo'], store_info['checkoutMerchantNo'], cnt, interval, client, progress_bar)
                    elif 'brand' in store_url:
                        answer_list, isSuccess = await get_brand_review(store_url,
                                                                        store_info['originProductNo'], store_info['checkoutMerchantNo'], cnt, interval, client, progress_bar)
                    # progress_bar 업데이트
                    current_progress = progress_bar.n
                    difference = 100 - current_progress
                    progress_bar.update(difference)
                    remaining_seconds = progress_bar._time() - progress_bar.start_t
                    if progress_bar.n == 0:
                        remaining_time = "알 수 없음"
                    else:
                        remaining_seconds = remaining_seconds * \
                            (progress_bar.total - progress_bar.n) / progress_bar.n
                        remaining_time = format_time(remaining_seconds)
                    dataInfo.refresh_buf[store_url]['progress'] = progress_bar.n
                    dataInfo.refresh_buf[store_url]['remaining_time'] = remaining_time
                    break
                except RequestError as exc:
                    msg = f'{traceback.format_exc()}'
                    asyncio.create_task(writelog(msg, False))
                    return None, isSuccess

        return list(dict.fromkeys(answer_list)), isSuccess

    # BrowserLikeClient 생성 (Playwright가 쿠키를 제공하므로 store_token만 필요)
    client = BrowserLikeClient(
        user_agent=dataInfo.User_Agent,
        store_token=dataInfo.store_token,
        proxy_config=proxyInfo.url)

    # refresh 버퍼에 추가
    async with dataInfo.refresh_buf_lock:
        dataInfo.refresh_buf[store_url] = dict()
        dataInfo.refresh_buf[store_url]['progress'] = 0
        dataInfo.refresh_buf[store_url]['remaining_time'] = "알 수 없음"

    answer_list, isSuccess = await collect_data(client)
    curLen = len(dataInfo.naverBuf.get(store_url, []))

    # 데이터를 다시 수집해야 하는 경우
    if not isSuccess:
        await asyncio.sleep(interval)
        answer_list, isSuccess = await collect_data(client)

    await client.close()

    # 수집이 완료되면 리프레시 버퍼에서 제거
    async with dataInfo.refresh_buf_lock:
        del dataInfo.refresh_buf[store_url]

    # 버퍼에 저장
    if bool(answer_list) and isSuccess:
        async with dataInfo.naverBuf_lock:
            if curLen > 0:
                # 중복되지 않은 새 값 찾기
                new_unique_items = [
                    item for item in answer_list if item not in dataInfo.naverBuf[store_url]]

                # 기존 정답 중 새로 찾은 값에 포함되는 값 찾기
                matching_items = [
                    item for item in dataInfo.naverBuf[store_url]
                    if item is None or any((item in answer or item.replace('\n', ' ') in answer.replace('\n', ' ')) and item != answer for answer in answer_list if answer is not None)
                ]

                # matching_items를 dataInfo.naverBuf[store_url]에서 제거
                dataInfo.naverBuf[store_url] = [
                    item for item in dataInfo.naverBuf[store_url] if item not in matching_items
                ]

                # 새로운 값 리스트 앞에 추가
                combined_list = new_unique_items + \
                    dataInfo.naverBuf[store_url]
                dataInfo.naverBuf[store_url] = combined_list
            else:
                dataInfo.naverBuf[store_url] = answer_list
            await naverBufInfo.save_pickle(dataInfo.naverBuf)

        msg = f'{primary_key} 정보수집 성공: ({curLen} → {len(dataInfo.naverBuf.get(store_url, []))})'
        asyncio.create_task(writelog(msg, False))
    else:
        msg = f'{primary_key} 정보수집 {"없음" if isSuccess else "실패"}: ({curLen} → {len(answer_list) if bool(answer_list) else 0}) {"🌑" if isSuccess else "🚨"}'
        asyncio.create_task(writelog(msg, False))

    if not pattern:
        return isSuccess, f'{curLen} → {len(dataInfo.naverBuf.get(store_url, []))}'

    return find_pattern_in_list(answer_list, pattern) if answer_list else None


def find_key_by_url(target_url):
    '''
    dataInfo.answerInfo 의 url 에 맞는 key 를 찾는 함수
    '''
    global dataInfo

    for key, value in dataInfo.answerInfo.items():
        # 첫 번째 요소가 리스트가 아닐 때와 일치하는지 확인
        if not isinstance(value[0], list) and value[0] == target_url:
            return key
        # 첫 번째 요소가 리스트일 때 그 안의 첫 번째 요소가 target_url과 일치하는지 확인
        elif isinstance(value[0], list) and value[0][0] == target_url:
            return key
    # URL을 찾지 못했을 경우 None 반환
    return None


def find_url_by_key(target_key):
    '''
    dataInfo.answerInfo 의 key 에 맞는 url 를 찾는 함수
    '''
    global dataInfo

    if target_key in dataInfo.answerInfo:
        fisrt_item = dataInfo.answerInfo[target_key][0]
        # 첫 번째 요소가 리스트가 아닐 때와 일치하는지 확인
        if not isinstance(fisrt_item, list) and ('http' in fisrt_item and not contains_any_except_link(fisrt_item, dataInfo.exceptLink)):
            return fisrt_item
        # 첫 번째 요소가 리스트일 때 그 안의 첫 번째 요소가 target_url과 일치하는지 확인
        elif isinstance(fisrt_item, list) and ('http' in fisrt_item[0] and not contains_any_except_link(fisrt_item[0], dataInfo.exceptLink)):
            return fisrt_item[0]

    # URL을 찾지 못했을 경우 None 반환
    return None


def print_list_counts(dictionary):
    '''
    딕셔너리 데이터에서 각 키에 해당하는 리스트의 아이템 수를 출력하는 함수
    '''
    global dataInfo
    result = []
    # 먼저 refresh_offset를 제외한 키와 값의 리스트를 생성
    keys_values = [(key, value) for key,
                   value in dataInfo.naverBuf.items() if key != 'refresh_offset']
    start_index = dataInfo.naverBuf.get('refresh_offset', 0)

    for index, (key, value) in enumerate(keys_values):
        title = find_key_by_url(key)
        if title:
            primary_key = title.split('-')[-1]
            result.append(
                f"{'→ ' if index == start_index else ''}{index+1:03}. {primary_key} : {len(value) if len(value) > dataInfo.maxRefreshPageCnt*10 else f'{len(value)} 📉'}")
        else:
            result.append(
                f"{'→ ' if index == start_index else ''}{index+1:03}. 삭제된 정보 : {len(value)} 🚨")

    return result


def normalize_spaces(text):
    '''
    2개 이상의 연속된 빈칸을 하나의 빈칸으로 변경
    '''
    return re.sub(r'[ \t]{2,}', ' ', text)


def extract_number_after_command(message_str: str, commands: List[str]) -> Optional[int]:
    """
    Checks if message_str starts with any of the commands followed by an optional space and a number.
    Returns the number if present, otherwise returns None.
    """
    # Validate inputs
    if not isinstance(message_str, str):
        raise ValueError("message_str must be a string")
    if not isinstance(commands, list):
        raise ValueError("commands must be a list of strings")
    if not all(isinstance(command, str) for command in commands):
        raise ValueError("all items in commands must be strings")

    # Iterate through each command in the list
    for command in commands:
        # Define the regex pattern for the current command
        pattern = rf'^{command}\s*(\d*)$'

        # Use re.match to check if the pattern matches the message_str
        match = re.match(pattern, message_str)

        if match:
            # Extract the number from the message
            number_str = match.group(1)

            if number_str:  # If there is a number
                return int(number_str)
            else:  # If there is no number
                return None

    return None


def get_buf_refresh_status():
    global dataInfo

    # 리프레시 현황 확인
    refMsgBuf = []
    if not dataInfo.refresh_buf:
        refMsgBuf.append("현재 리프래시 중인 항목이 없습니다. 😎")
    else:
        for key in dataInfo.refresh_list:
            title = find_key_by_url(key)
            if key in dataInfo.refresh_buf:
                refMsgBuf.append(
                    f"⏳ {title} : {dataInfo.refresh_buf[key]['progress']}%, 남은시간 : {dataInfo.refresh_buf[key]['remaining_time']}")
            else:
                refMsgBuf.append(
                    f"📁 {title} : {dataInfo.refresh_list[key]['PageCnt']} 수집대기중")

    return '\n'.join(refMsgBuf)


async def refresh_buf(key: str, PageCnt: int, inverval: int, isTelegram: bool, chatID: int):
    '''
    문제 buf 를 리프레시 하는 함수
    key : 문제 url
    PageCnt : 리프레시할 페이지 수
    inverval : 리프레시 간격
    isTelegram : 텔레그램에서 실행 여부
    chatID : 텔레그램 채팅방 ID
    '''
    global dataInfo

    if key not in dataInfo.answerInfo:
        msg = f'{key} 라는 문제가 없습니다. 리프래쉬 하고 싶은 문제를 정확하게 입력하거나 번호를 선택하세요! 🙄'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)
    elif 'smartstore.naver.com' in dataInfo.answerInfo[key][0] or 'brand.naver.com' in dataInfo.answerInfo[key][0]:
        # 스마트스토어 정답찾기
        store_url = dataInfo.answerInfo[key][0]
        # 이미 리프레시 대기열에 있는지 확인
        if store_url in dataInfo.refresh_list:
            msg = f"{key} 문제는 이미 리프레시 대기중 입니다. {dataInfo.refresh_list[store_url]['PageCnt']} 페이지를 가져옵니다.. ♻"
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            return

        # 리프레시 대기열에 추가
        async with dataInfo.refresh_list_lock:
            dataInfo.refresh_list[store_url] = dict()
            dataInfo.refresh_list[store_url]['title'] = key
            dataInfo.refresh_list[store_url]['PageCnt'] = PageCnt

        msg = f'{key} 문제의 정보 갱신을 위해 {PageCnt} 페이지를 가져옵니다.. ♻'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)

        # 데이터 재수집
        while True:
            async with dataInfo.refresh_buf_lock:
                if len(dataInfo.refresh_buf) < dataInfo.maxWorkers:
                    break
            # Wait for 1 second before checking again
            await asyncio.sleep(1)
        await asyncio.sleep(inverval)  # 이전 정보수집과의 인터벌을 위한 대기시간
        backup_result, backup_count_info = await get_store_answer(store_url, PageCnt, inverval, None)

        # 리프레시 대기열에서 제거
        async with dataInfo.refresh_list_lock:
            del dataInfo.refresh_list[store_url]

        msg = f'{key} 정보수집결과: {"성공 😄" if backup_result else "실패 😭"}({backup_count_info})'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)
    elif 'place.naver.com' in dataInfo.answerInfo[key][0]:
        place_url = dataInfo.answerInfo[key][0]
        # 이미 리프레시 대기열에 있는지 확인
        if place_url in dataInfo.refresh_list:
            msg = f"{key} 문제는 이미 리프레시 대기중 입니다. {dataInfo.refresh_list[place_url]['PageCnt']} 페이지를 가져옵니다.. ♻"
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            return

        # 리프레시 대기열에 추가
        async with dataInfo.refresh_list_lock:
            dataInfo.refresh_list[place_url] = dict()
            dataInfo.refresh_list[place_url]['title'] = key
            dataInfo.refresh_list[place_url]['PageCnt'] = PageCnt

        # place 정답찾기
        msg = f'{key} 문제의 정보 갱신을 위해 {PageCnt} 페이지를 가져옵니다.. ♻'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)

        # 데이터 재수집
        while True:
            async with dataInfo.refresh_buf_lock:
                if len(dataInfo.refresh_buf) < dataInfo.maxWorkers:
                    break
            # Wait for 1 second before checking again
            await asyncio.sleep(1)
        await asyncio.sleep(inverval)  # 이전 정보수집과의 인터벌을 위한 대기시간
        backup_result, backup_count_info = await get_place_answer(place_url, PageCnt, inverval, None)

        # 리프레시 대기열에서 제거
        async with dataInfo.refresh_list_lock:
            del dataInfo.refresh_list[place_url]

        msg = f'{key} 정보수집결과: {"성공 😄" if backup_result else "실패 😭"}({backup_count_info})'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)
    elif 'place.map.kakao.com' in dataInfo.answerInfo[key][0]:
        place_url = dataInfo.answerInfo[key][0]
        # 이미 리프레시 대기열에 있는지 확인
        if place_url in dataInfo.refresh_list:
            msg = f"{key} 문제는 이미 리프레시 대기중 입니다. {dataInfo.refresh_list[place_url]['PageCnt']} 페이지를 가져옵니다.. ♻"
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(

                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            return

        # 리프레시 대기열에 추가
        async with dataInfo.refresh_list_lock:
            dataInfo.refresh_list[place_url] = dict()
            dataInfo.refresh_list[place_url]['title'] = key
            dataInfo.refresh_list[place_url]['PageCnt'] = PageCnt

        # place 정답찾기
        msg = f'{key} 문제의 정보 갱신을 위해 {PageCnt} 페이지를 가져옵니다.. ♻'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)

        # 데이터 재수집
        while True:
            async with dataInfo.refresh_buf_lock:
                if len(dataInfo.refresh_buf) < dataInfo.maxWorkers:
                    break
            # Wait for 1 second before checking again
            await asyncio.sleep(1)
        await asyncio.sleep(inverval)  # 이전 정보수집과의 인터벌을 위한 대기시간
        backup_result, backup_count_info = await get_kakao_place_answer(
            place_url, PageCnt, inverval, None)

        # 리프레시 대기열에서 제거
        async with dataInfo.refresh_list_lock:
            del dataInfo.refresh_list[place_url]

        msg = f'{key} 정보수집결과: {"성공 😄" if backup_result else "실패 😭"}({backup_count_info})'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)
    else:
        msg = f'{key} 리프래쉬를 위한 정보가 부족하여 정답을 찾을 수 없습니다. 🤨'
        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)

    return


async def run_admin_command(chatID, userID, message_str, message_edit, reply_message_str, isTelegram=True):
    '''
    관리자 메뉴를 실행하는 함수
    chatID : chatID
    userID : 사용자 ID
    message_str : 메시지 원문
    message_edit : 메시지 원문에서 띄어씌기 제거
    reply_message_str : reply 메시지라면 원문
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo, answerKeyInfo

    def is_command(command_list: list, message_str: str) -> bool:
        '''
        주어진 커맨드 리스트와 일치하는 커맨드인지 확인하는 함수
        뒤에 숫자가 와도 됨
        '''
        # Join the command list into a regex pattern
        pattern = r'^(' + '|'.join(command_list) + r')\s*\d*$'

        # Use re.match to check if the pattern matches the message_str
        if re.match(pattern, message_str):
            return True
        else:
            return False

    try:
        message_str = message_str[2:].lower()
        message_edit = message_edit[2:]
        if not bool(message_str):
            # 조치할 명령어가 없으면 초기화
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_title'] = None
                dataInfo.answerKey[f'{userID}_title_cancel'] = None
                dataInfo.answerKey[f'{userID}_answer_cancel'] = None
                dataInfo.answerKey[f'{userID}_naver_key'] = None
                dataInfo.answerKey[f'{userID}_naver_cancel_key'] = None
                dataInfo.answerKey[f'{userID}_naver_cancel'] = None
                # dataInfo.answerKey[f'{userID}_title_image'] = None
                # dataInfo.answerKey[f'{userID}_title_buf_image'] = None
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            # 설정값 확인
            msg = f'📌 정답문제 : {dataInfo.answerKey.get(f"{userID}_title", "없음")}\n' \
                f'📌 취소문제 : {dataInfo.answerKey.get(f"{userID}_title_cancel", "없음")}\n' \
                f'📌 취소정답 : {dataInfo.answerKey.get(f"{userID}_answer_cancel", "없음")}\n' \
                f'📌 정답후보 : {dataInfo.answerKey.get(f"{userID}_title_buf", "없음")}\n' \
                f'📌 버퍼입력키 : {dataInfo.answerKey.get(f"{userID}_naver_key", "없음")}\n' \
                f'📌 버퍼취소키 : {dataInfo.answerKey.get(f"{userID}_naver_cancel_key", "없음")}\n' \
                f'📌 버퍼취소값: {dataInfo.answerKey.get(f"{userID}_naver_cancel", "없음")}'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif message_str == 'alert' or message_str == 'a':
            # alert 모드 토글
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_alert'] = True if not dataInfo.answerKey.get(
                    f'{userID}_alert', False) else False
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            msg = f'alert 모드가 {"ON" if dataInfo.answerKey.get(f"{userID}_alert", False) else "OFF"} 되었습니다. 👀'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif message_str == 'user' or message_str == 'u':
            # user list 조회
            # userList = [
            #     f"{index + 1}. {dataInfo.userInfo[key].get('username', key)} ({key})" + (
            #         ", premium" if key in dataInfo.premiumMember else "")
            #     for index, key in enumerate(dataInfo.userInfo.keys())
            # ]
            userList = []
            for idx, userID in enumerate(dataInfo.userInfo):
                msg = f'{idx+1}. {dataInfo.userInfo[userID].get("username", userID)} ({userID})\n' \
                    f'📌 정답알림 갯수 : {dataInfo.userInfo[userID].get("num_items", dataInfo.maxAnswerCnt)}\n' \
                    f'📌 검색어 출력 : {"문제와 답을 한번에" if dataInfo.userInfo[userID].get("nonList", False) else "선택한 문제의 답을"} 출력합니다.\n' \
                    f'📌 이미지 출력: 문제 이미지 크기를 {"작게" if dataInfo.userInfo[userID].get("image", True) else "크게"} 출력합니다.'
                if userID in dataInfo.premiumMember:
                    msg += '\n📌 등급 : premium ✨'
                msg += '\n'
                userList.append(msg)

            msg = f'🎫 사용자 현황 📑\n' + '\n'.join(userList)
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif message_str == 'status' or message_str == 's' or message_str == 'ㄴ':
            # 리프레시 현황 확인
            refMsg = get_buf_refresh_status()
            # refresh_naver_buf 리프레시 현황 확인
            if not dataInfo.naverBuf_list:
                navMsg = "현재 refresh_naver_buf 가 실행중이지 않아요 😎"
            else:
                navMsg = f"⏳ {dict_values_to_string(dataInfo.naverBuf_list)}"

            # 설정값 확인
            msg = f'📌 알림모드 : {dataInfo.answerKey.get(f"{userID}_noti", False)}\n' \
                f'📌 Alert모드 : {dataInfo.answerKey.get(f"{userID}_alert", False)}\n' \
                f'📌 채널알림모드 : {not dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False)}\n' \
                f'📌 알림갯수 : {dataInfo.userInfo[userID].get("num_items", "전체")}\n' \
                f'📌 검색어 출력 : {"문제와 답을 한번에" if dataInfo.userInfo[userID].get("nonList", False) else "선택한 문제의 답을"} 출력합니다.\n' \
                f'📌 이미지 출력 : 문제 이미지 크기를 {"작게" if dataInfo.userInfo[userID].get("image", True) else "크게"} 출력합니다.\n' \
                f'📌 정답문제 : {dataInfo.answerKey.get(f"{userID}_title", "없음")}\n' \
                f'📌 정답후보 : {dataInfo.answerKey.get(f"{userID}_title_buf", "없음")}\n' \
                f'📌 취소문제 : {dataInfo.answerKey.get(f"{userID}_title_cancel", "없음")}\n' \
                f'📌 취소정답 : {dataInfo.answerKey.get(f"{userID}_answer_cancel", "없음")}\n' \
                f'📌 취소IDS : {dataInfo.answerKey.get(f"{userID}_cancel_ids", "없음")}\n' \
                f'📌 버퍼입력키 : {dataInfo.answerKey.get(f"{userID}_naver_key", "없음")}\n' \
                f'📌 버퍼취소키 : {dataInfo.answerKey.get(f"{userID}_naver_cancel_key", "없음")}\n' \
                f'📌 버퍼취소값 : {dataInfo.answerKey.get(f"{userID}_naver_cancel", "없음")}\n' \
                f'📌 naverBuf : {len(dataInfo.naverBuf)}\n' \
                f'📌 refresh_buf : {refMsg}\n' \
                f'📌 refresh_naver_buf : {navMsg}'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif message_str == 'total' or message_str == 't' or message_str == 'ㅅ':
            # naverBuf 통계
            key_count = print_list_counts(dataInfo.naverBuf)
            msgList = [key_count[i:i + 100]
                       for i in range(0, len(key_count), 100)]
            if isTelegram:
                asyncio.gather(*(asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, "\n".join(msg), disable_notification=True)) for msg in msgList))
            else:
                list(map(lambda msg: print("\n".join(msg)), msgList))
            # for msg in msgList:
            #     summary = "\n".join(msg)
            #     if isTelegram:
            #         await telegramInfo.botInfo.bot.send_message(chatID, summary, disable_notification=True)
            #         # await asyncio.sleep(dataInfo.sendInterval)
            #     else:
            #         print(summary)
        elif message_str == 'noti' or message_str == 'n':
            # 채널에 정답알림 모드 활성화
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_noti'] = True
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            msg = f'채널에 정답알림 모드가 활성화 되었습니다. 🔔'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            # 정답제목 초기화
            dataInfo.answerKey[f'{userID}_title'] = None
        elif message_str == 'mute' or message_str == 'm':
            # 채널에 정답알림 모드 비활성화
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_noti'] = False
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            msg = f'채널에 정답알림 모드가 비활성화 되었습니다. 🤐'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            # 정답제목 초기화
            dataInfo.answerKey[f'{userID}_title'] = None
        elif message_str == 'reload' or message_str == 'r':
            changes, deletions = await update_answerInfo()
            if bool(changes) or bool(deletions):
                messages = []
                if changes:  # changes에 항목이 있으면
                    messages.append(f'추가된 정보: {changes}')
                if deletions:  # deletions에 항목이 있으면
                    messages.append(f'삭제된 정보: {deletions}')
                msg = '\n'.join(messages)
            else:
                msg = f'{dataInfo.answerFilename} 파일에 업데이트된 내용이 없습니다. ✅'

            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            print(msg)
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_title'] = None
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
        elif message_str == 'link' or message_str == 'l':
            non_url_keys = find_keys_with_non_url_first_item(
                dataInfo.answerInfo)
            # non_id_smartstore = find_keys_with_short_list(
            #     dataInfo.answerInfo)
            if not bool(non_url_keys):
                msg = f'모두 정상입니다! 👍'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
            else:
                msg = f'URL이 없는 key : {non_url_keys}'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
        elif message_str == 'ref':
            # 리프레시 현황 확인
            msg = get_buf_refresh_status()
            # 리프레시 현황 출력
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print('\n'.join(msg))
        elif message_str == 'nav':
            # 리프레시 현황 확인
            if not dataInfo.naverBuf_list:
                msg = "현재 refresh_naver_buf 가 실행중이지 않아요 😎"
            else:
                msg = f"⏳ refresh_naver_buf : {dict_values_to_string(dataInfo.naverBuf_list)}"

            # 리프레시 현황 출력
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif is_command(['get', 'g'], message_str):
            # 갱신할 문제 갯수가 있는지 확인
            try:
                maxRefresh = extract_number_after_command(
                    message_str, ['get', 'g'])
                if not maxRefresh:
                    maxRefresh = dataInfo.maxRefresh
            except ValueError as e:
                err_msg = f"Error extract_number_after_command '{message_str}': {e} 🙄"
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, err_msg, disable_notification=True))
                else:
                    print(err_msg)
                return

            msg = f'naverBuf 를 {maxRefresh} 개 리프래쉬 합니다. ♻'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)

            await refresh_naver_buf('refresh_naver_buf', maxRefresh, isTelegram)

            msg = f'naverBuf 리프래쉬 {maxRefresh} 개를 완료했습니다. 💯'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif is_command(['buf', 'b'], message_str):
            # 갱신할 page 갯수가 있는지 확인
            try:
                PageCnt = extract_number_after_command(
                    message_str, ['buf', 'b'])
                if not PageCnt:
                    PageCnt = dataInfo.maxBackupPageCnt
                inverval = dataInfo.backupInterval if PageCnt > dataInfo.maxPageCnt else dataInfo.naverInterval
            except ValueError as e:
                err_msg = f"Error extract_number_after_command '{message_str}': {e} 🙄"
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, err_msg, disable_notification=True))
                else:
                    print(err_msg)
                return

            # buf 리프래쉬
            if not bool(dataInfo.answerKey.get(f"{userID}_title_buf", False)):
                msg = f'naverBuf를 리프래쉬 할 문제를 먼저 검색하세요. 🙄'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
                return
            key = dataInfo.answerKey[f'{userID}_title_buf']
            asyncio.create_task(refresh_buf(
                key, PageCnt, inverval, isTelegram, chatID))
        elif message_str == 'count' or message_str == 'c':
            # 수집한 naver buf 갯수 조회
            if not bool(dataInfo.answerKey[f'{userID}_title_buf']):
                msg = f'naverBuf 에 정보가 있는지 확인할 문제를 선택하세요. 🙄'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
                return
            key = dataInfo.answerKey[f'{userID}_title_buf']
            if key not in dataInfo.answerInfo:
                msg = f'{key} 라는 문제가 없습니다. 정보가 있는지 확인할 문제를 다시 선택하세요. 🤔'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
            elif 'smartstore.naver.com' in dataInfo.answerInfo[key][0] or 'brand.naver.com' in dataInfo.answerInfo[key][0]:
                # 스마트스토어 정답찾기
                store_url = dataInfo.answerInfo[key][0]
                # 버퍼 갯수 확인
                if store_url in dataInfo.naverBuf:
                    msg = f"{key} : {len(dataInfo.naverBuf[store_url])} 개"
                else:
                    msg = f"{key} : 검색정보 없음! 🤔"
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
            elif 'place.naver.com' in dataInfo.answerInfo[key][0]:
                place_url = dataInfo.answerInfo[key][0]
                # 버퍼 갯수 확인
                if place_url in dataInfo.naverBuf:
                    msg = f"{key} : {len(dataInfo.naverBuf[place_url])} 개"
                else:
                    msg = f"{key} : 검색정보 없음! 🤔"
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
            elif 'place.map.kakao.com' in dataInfo.answerInfo[key][0]:
                place_url = dataInfo.answerInfo[key][0]
                # 버퍼 갯수 확인
                if place_url in dataInfo.naverBuf:
                    msg = f"{key} : {len(dataInfo.naverBuf[place_url])} 개"
                else:
                    msg = f"{key} : 검색정보 없음! 🤔"
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
            else:
                msg = f'{key} 는 올바른 URL이 아닙니다. 관리자에게 문의하세요. 😣'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
        elif '>>' in message_str:
            # 기출문제 제목 변경
            keys = message_str.split('>>')
            if len(keys) == 2:
                old_key, new_key = keys[0].replace(
                    ' ', ''), keys[1].replace(' ', '')
                if await change_key(old_key, new_key):
                    msg = f"{old_key}→{new_key} 변경완료! 😄"
                else:
                    msg = f"{old_key} 를 찾을 수 없습니다. 🤨"
            else:
                msg = f"올바른 제목변경 양식이 아닙니다! 😖"
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        else:
            update_result = await update_naver_buf(chatID, userID, message_str, message_edit, reply_message_str, isTelegram)
            if not update_result:
                msg = f'{message_str} 라는 명령어는 없습니다. 😗\n' \
                    f'정답제목 : {dataInfo.answerKey.get(f"{userID}_title", "없음")}\n' \
                    f'임시제목: {dataInfo.answerKey.get(f"{userID}_title_buf", "없음")}'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return


def remove_and_return_items_by_partial_match(result, partial_content):
    """
    부분 일치를 사용하여 리스트에서 항목을 제거하고 제거된 항목들을 반환합니다.

    :param result: 항목을 제거할 원본 리스트
    :param partial_content: 찾을 부분 문자열
    :return: (제거된 항목들의 리스트, 남은 항목들의 리스트, 작업 성공 여부)
    """
    removed_items = []
    remaining_items = []

    for item in result:
        if partial_content in item:
            removed_items.append(item)
        else:
            remaining_items.append(item)

    # 원본 리스트를 남은 항목들로 업데이트
    result[:] = remaining_items

    # 제거된 항목이 있으면 True, 없으면 False 반환
    success = len(removed_items) > 0

    return removed_items, success


async def update_naver_buf(chatID, userID, message_str, message_edit, reply_message_str, isTelegram=True):
    '''
    naver buf 를 업데이트 하는 함수
    chatID : chatID
    userID : 사용자 ID
    message_str : 메시지 원문
    message_edit : 메시지 원문에서 띄어씌기 제거
    reply_message_str : reply 메시지라면 원문
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo

    result = True
    try:
        # dataInfo.answerKey 업데이트
        if message_str == '버퍼' and not bool(reply_message_str):
            # 임시제목이 있으면 정답제목으로 간주
            if dataInfo.answerKey.get(f'{userID}_title_buf', False):
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_naver_key'] = find_url_by_key(
                        dataInfo.answerKey[f'{userID}_title_buf'])
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)

                # dataInfo.answerKey[f'{userID}_title_image'] = dataInfo.answerKey.get(f'{userID}_title_buf_image', None)
                msg = f'버퍼 업데이트 key: {dataInfo.answerKey.get(f"{userID}_naver_key", "없음")} 🎯'
            else:
                msg = "버퍼를 업데이트 할 제목을 입력하세요. 😓"
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif (message_str == '버퍼취소' or message_str == '버퍼아님'):
            if not (bool(dataInfo.answerKey.get(f'{userID}_naver_cancel_key', False)) and bool(dataInfo.answerKey.get(f'{userID}_naver_cancel', False))):
                msg = "다시 시도해주세요! 😱"
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
            else:
                # 버퍼에서 답 삭제
                if dataInfo.answerKey[f'{userID}_naver_cancel'] in dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_cancel_key']]:
                    async with dataInfo.naverBuf_lock:
                        dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_cancel_key']].remove(
                            dataInfo.answerKey[f'{userID}_naver_cancel'])
                        msg = f"{dataInfo.answerKey[f'{userID}_naver_cancel_key']} 에서 {dataInfo.answerKey[f'{userID}_naver_cancel']} 를 삭제했습니다."
                        dataInfo.answerKey[f'{userID}_naver_key'] = None
                        dataInfo.answerKey[f'{userID}_naver_cancel_key'] = None
                        dataInfo.answerKey[f'{userID}_naver_cancel'] = None
                        await naverBufInfo.save_pickle(dataInfo.naverBuf)
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
        elif message_str[-2:] == '버퍼' and not bool(reply_message_str):
            # 메시지 마지막 글자가 "버퍼" 이면 버퍼를 입력할 naver buf 제목
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_title'] = message_edit.replace(
                    "답", "").replace(" ", "")
                dataInfo.answerKey[f'{userID}_naver_key'] = find_url_by_key(
                    dataInfo.answerKey[f'{userID}_title'])
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            msg = f'버퍼 업데이트 제목: {dataInfo.answerKey.get(f"{userID}_title", "없음")} 🎯'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif bool(dataInfo.answerKey.get(f'{userID}_naver_key', False)) or \
                (message_str == '버퍼' and bool(reply_message_str) and bool(dataInfo.answerKey.get(f'{userID}_title_buf', False))):

            # naver buf key가 없으면 제목후보로 key 확인
            if not bool(dataInfo.answerKey.get(f'{userID}_naver_key', False)):
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_naver_key'] = find_url_by_key(
                        dataInfo.answerKey[f'{userID}_title_buf'])
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)

            # reply 로 버퍼를 입력하는 경우 원문을 버퍼에 저장
            if message_str == '버퍼' and bool(reply_message_str):
                buf_str = reply_message_str
            else:
                buf_str = message_str

            if buf_str.startswith('-'):
                async with dataInfo.naverBuf_lock:
                    # 버퍼에서 제거
                    removed_items, success = remove_and_return_items_by_partial_match(
                        dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']], buf_str[1:])
                    if success:
                        await naverBufInfo.save_pickle(dataInfo.naverBuf)
                        for item in removed_items:
                            msg = f"{dataInfo.answerKey[f'{userID}_naver_key']} 에서 {item} 를 삭제했습니다."
                            if isTelegram:
                                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                    chatID, msg, disable_notification=True))
                            else:
                                print(msg)
                        # dataInfo.answerKey[f'{userID}_naver_key'] = None
                        dataInfo.answerKey[f'{userID}_naver_cancel_key'] = None
                        dataInfo.answerKey[f'{userID}_naver_cancel'] = None
                    else:
                        msg = f"버퍼에 {buf_str[1:]} 와 부분일치하는 항목이 없습니다."
                        if isTelegram:
                            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                chatID, msg, disable_notification=True))
                        else:
                            print(msg)
            else:
                # 버퍼에 추가
                if dataInfo.answerKey[f'{userID}_naver_key'] not in dataInfo.naverBuf:
                    async with dataInfo.naverBuf_lock:
                        dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']] = [
                        ]
                if buf_str in dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']]:
                    msg = f"{dataInfo.answerKey[f'{userID}_naver_key']} 버퍼에 {buf_str} 가 이미 있습니다. 😉"
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
                else:
                    async with dataInfo.naverBuf_lock:
                        # 기존 정답 중 새로 찾은 값에 포함되는 값 찾기
                        matching_items = [
                            item for item in dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']]
                            if item is None or ((item in buf_str or item.replace('\n', ' ') in buf_str.replace('\n', ' ')) and item != buf_str)
                        ]

                        # matching_items를 dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']]에서 제거
                        dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']] = [
                            item for item in dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']] if item not in matching_items
                        ]
                        dataInfo.naverBuf[dataInfo.answerKey[f'{userID}_naver_key']].insert(
                            0, buf_str)
                        dataInfo.answerKey[f'{userID}_naver_cancel_key'] = dataInfo.answerKey[f'{userID}_naver_key']
                        dataInfo.answerKey[f'{userID}_naver_cancel'] = buf_str
                        await naverBufInfo.save_pickle(dataInfo.naverBuf)
                        msg = f"{dataInfo.answerKey[f'{userID}_naver_cancel_key']} 에 {buf_str} 를 추가했습니다."
                        if isTelegram:
                            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                chatID, msg, disable_notification=True))
                        else:
                            print(msg)
        else:
            # dataInfo.naverBuf 업데이트 사항이 아니면 false 리턴
            result = False
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return result


async def update_answer_data(chatID, userID, message_str, message_edit, reply_message_str, isTelegram=True):
    '''
    정답정보를 업데이트 하는 함수
    chatID : chatID
    userID : 사용자 ID
    message_str : 메시지 원문
    message_edit : 메시지 원문에서 띄어씌기 제거
    reply_message_str : reply 메시지라면 원문
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo

    result = True
    try:
        # dataInfo.answerKey 업데이트
        if message_str in dataInfo.answerKeyword and not bool(reply_message_str):
            # 임시제목이 있으면 정답제목으로 간주
            if dataInfo.answerKey.get(f'{userID}_title_buf', False):
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_title'] = dataInfo.answerKey[f'{userID}_title_buf']
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)

                # dataInfo.answerKey[f'{userID}_title_image'] = dataInfo.answerKey.get(f'{userID}_title_buf_image', None)
                msg = f'정답제목: {dataInfo.answerKey.get(f"{userID}_title", "없음")} 🎯'
            else:
                msg = "정답을 입력할 제목을 입력하세요. 😓"
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif (message_str == '답취소' or message_str == '답아님'):
            if not (bool(dataInfo.answerKey.get(f'{userID}_title_cancel', False)) and bool(dataInfo.answerKey.get(f'{userID}_answer_cancel', False))):
                msg = "다시 시도해주세요! 😱"
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
            else:
                if dataInfo.answerKey.get(f'{userID}_noti', False) and \
                        ("http" not in message_str or contains_any_except_link(message_str, dataInfo.exceptLink)):
                    # 일림모드이고 답아님 이면 단체방 정답삭제 또는 정답아님 알림
                    if bool(dataInfo.answerKey.get(f'{userID}_cancel_ids', None)):
                        deleteResult = await telegramInfo.botInfo.bot.delete_messages(telegramInfo.channelChatID, dataInfo.answerKey[f'{userID}_cancel_ids'])
                        if not deleteResult:
                            asyncio.create_task(telegramInfo.botInfo.bot.send_message(telegramInfo.channelChatID,
                                                                                      f'❌ {dataInfo.answerKey[f"{userID}_answer_cancel"]} 정답아님!! ❌', disable_notification=True))
                    elif isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(telegramInfo.channelChatID,
                                                                                  f'❌ {dataInfo.answerKey[f"{userID}_answer_cancel"]} 정답아님!! ❌', disable_notification=True))
                # 문제에서 답 삭제
                sameAsBefore = await add_answerInfo(
                    dataInfo.answerKey[f'{userID}_title_cancel'], "-"+dataInfo.answerKey[f'{userID}_answer_cancel'], chatID, isTelegram)
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_title_cancel'] = None
                    dataInfo.answerKey[f'{userID}_answer_cancel'] = None
                    dataInfo.answerKey[f'{userID}_cancel_ids'] = None
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)
        elif message_str[-1] == '답' and not bool(reply_message_str):
            # 메시지 마지막 글자가 "답" 이면 답을 입력할 기출문제 제목
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_title'] = message_edit.replace(
                    "답", "").replace(" ", "")
                await answerKeyInfo.save_pickle(dataInfo.answerKey)
            msg = f'정답제목 : {dataInfo.answerKey.get(f"{userID}_title", "없음")} 🎯'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif bool(dataInfo.answerKey.get(f'{userID}_title', False)) or \
                (message_str in dataInfo.answerKeyword and bool(reply_message_str)):
            # and bool(dataInfo.answerKey.get(f'{userID}_title_buf', False)) ??

            # reply 로 답을 입력하는 경우 원문을 정답으로 지정
            if message_str in dataInfo.answerKeyword and bool(reply_message_str):
                answer_str = reply_message_str
            else:
                answer_str = message_str

            # 정답제목이 없으면 제목후보를 제목으로 지정
            if not bool(dataInfo.answerKey.get(f'{userID}_title', False)):
                async with dataInfo.answerKey_lock:
                    if dataInfo.answerKey[f'{userID}_title_buf']:
                        dataInfo.answerKey[f'{userID}_title'] = dataInfo.answerKey[f'{userID}_title_buf']
                    elif answer_str in dataInfo.answerKey.get(f'{userID}_answer_info', {}):
                        dataInfo.answerKey[f'{userID}_title'] = dataInfo.answerKey[f'{userID}_answer_info'][answer_str]
                    else:
                        dataInfo.answerKey[f'{userID}_title'] = None
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)

            # 채널방 알림
            sendResult = None
            if isTelegram and dataInfo.answerKey.get(f'{userID}_noti', False) and \
                    ("http" not in message_str or contains_any_except_link(message_str, dataInfo.exceptLink)):
                # 알림모드이고 정답링크가 아니면 단체방에 정답 알림
                if dataInfo.answerKey.get(f'{userID}_title', False):
                    sendResult = await telegramInfo.botInfo.bot.send_message(telegramInfo.channelChatID, f"{dataInfo.answerKey[f'{userID}_title']} 답 🎯", disable_notification=True)
                    title_cance_id = sendResult.message_id
                    # await asyncio.sleep(dataInfo.sendInterval)
                else:
                    title_cance_id = 0

                if not answer_str.startswith('-'):
                    sendResult = await telegramInfo.botInfo.bot.send_message(telegramInfo.channelChatID, answer_str, disable_notification=dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False))
                    answer_cancel_id = sendResult.message_id
                    # 답취소를 대비해서 텔레그램 채널 메시지ID 저장
                    async with dataInfo.answerKey_lock:
                        dataInfo.answerKey[f'{userID}_cancel_ids'] = [
                            title_cance_id, answer_cancel_id]
                else:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        telegramInfo.channelChatID, f'❌ {answer_str[1:]} 정답아님!! ❌', disable_notification=True))

            # 정답 제목이 있는 경우
            if dataInfo.answerKey.get(f'{userID}_title', False):
                # 답취소를 대비해서 제목과 답을 따로 저장
                if not answer_str.startswith('-'):
                    async with dataInfo.answerKey_lock:
                        dataInfo.answerKey[f'{userID}_title_cancel'] = dataInfo.answerKey[f'{userID}_title']
                        dataInfo.answerKey[f'{userID}_answer_cancel'] = answer_str
                        await answerKeyInfo.save_pickle(dataInfo.answerKey)

                # 기출문제 정답정보 업데이트
                sameAsBefore = await add_answerInfo(
                    dataInfo.answerKey[f'{userID}_title'], answer_str, chatID, isTelegram)

                # 이전과 정답이 달라지지 않은 경우
                if sameAsBefore and sendResult:
                    await sendResult.set_reaction(reaction='👌')
                    # await sendResult.set_reaction(reaction=ReactionTypeEmoji('👌'))

                # 정답입력 제목 정보 초기화
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_title'] = None
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)

                # 기출문제 중복체크
                dupList = dataInfo.find_duplicate_urls()
                if isTelegram:
                    asyncio.gather(
                        *[telegramInfo.botInfo.bot.send_message(chatID, dup) for dup in dupList])
                else:
                    list(map(lambda dup: print(dup), dupList))

                # for dup in dupList:
                #     if isTelegram:
                #         await telegramInfo.botInfo.bot.send_message(chatID, dup)
                #         # await asyncio.sleep(dataInfo.sendInterval)
                #     else:
                #         print(dup)
        else:
            # dataInfo.answerKey 업데이트 사항이 아니면 false 리턴
            result = False
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return result


async def update_user_items_count(chatID, userID, message_edit, isTelegram=True):
    '''
    사용자에게 알려줄 정답갯수를 업데이트 하는 함수
    chatID : chatID
    userID : 사용자 ID
    message_str : 메시지 원문
    message_edit : 메시지 원문에서 띄어씌기 제거
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo

    edit_num_items = dataInfo.userInfo[userID].get(
        'num_items', dataInfo.maxAnswerCnt)
    try:
        parts = message_edit.rsplit(':', 1)  # 마지막 콜론을 기준으로 분리합니다.
        if parts[-1].isdigit():  # 콜론 뒤의 부분이 숫자인지 확인합니다.
            num_items = int(parts[-1])  # 숫자를 추출합니다.
            async with dataInfo.userInfo_lock:
                if num_items > dataInfo.maxAnswerBuf:
                    edit_num_items = dataInfo.maxAnswerBuf
                elif num_items > 0:
                    edit_num_items = num_items
                else:
                    edit_num_items = dataInfo.maxAnswerBuf
                await userInfo.save_pickle(dataInfo.userInfo)

            # 숫자 앞의 부분을 message_edit_words로 설정합니다.
            message_edit = parts[0]
            if not bool(message_edit):
                dataInfo.userInfo[userID]['num_items'] = edit_num_items
                msg = f'정답 알림 갯수를 {dataInfo.userInfo[userID]["num_items"]} 개로 설정합니다. 😎'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return edit_num_items, message_edit


async def get_Answer_For_Selected_Problem(chatID, userID, message_edit, isTelegram=True):
    '''
    사용자에게 알려줄 정답갯수를 업데이트 하는 함수
    chatID : chatID
    userID : 사용자 ID
    message_str : 메시지 원문
    message_edit : 메시지 원문에서 띄어씌기 제거
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo

    try:
        idNum = int(message_edit) - 1
        answerSize = len(dataInfo.userInfo[userID]['answer'])

        if answerSize == 0:
            msg = f'먼저 문제를 검색해주세요! 😅'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            return
        elif (idNum+1) > answerSize or idNum < 0:
            msg = f'1 부터 {answerSize} 사이의 숫자를 입력하세요. 🙄'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            return

        # 프리미엄회원인 경우
        if userID in dataInfo.premiumMember:
            # 정답 찾기를 할지 모르니 일단 저장
            async with dataInfo.userInfo_lock:
                dataInfo.userInfo[userID]['title'] = dataInfo.userInfo[userID]['answer'][idNum][0][:-4]

        # 관리자는 정답후보로도 저장
        if userID in dataInfo.answerManageMember:
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_title_buf'] = dataInfo.userInfo[userID]['title']
                await answerKeyInfo.save_pickle(dataInfo.answerKey)

        if not dataInfo.userInfo[userID].get('nonList', False):
            # 정답 알림
            for idx, line in enumerate(dataInfo.userInfo[userID]['answer'][idNum]):
                if 'http' in line and not contains_any_except_link(line, dataInfo.exceptLink):
                    continue
                elif contains_any_except_link(line, dataInfo.exceptLink):
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, line, disable_notification=True, disable_web_page_preview=True))
                    else:
                        print(line)
                else:
                    if isTelegram:
                        if idx != 0:
                            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                chatID, line, disable_notification=True))
                        else:
                            await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True)
                        # await asyncio.sleep(dataInfo.sendInterval)
                    else:
                        print(line)
        elif userID in dataInfo.premiumMember:
            # 문제선택 알림
            msg = f'{dataInfo.userInfo[userID]["title"]} 💡 을 선택했습니다. \n\n' \
                f'"*" 검색을 시작해보세요~ 🧐'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return


def remove_special_chars_ends(text):
    '''
    문장의 앞뒤 특수문자를 제거하는 함수
    '''
    # 첫 번째 단어 문자(한글 포함) 앞의 특수문자 제거
    text = re.sub(r'^[^\w가-힣]+', '', text)
    # 마지막 단어 문자(한글 포함) 뒤의 특수문자 제거
    text = re.sub(r'[^\w가-힣]+$', '', text)
    return text


def remove_substrings(items):
    # 문자열 길이를 기준으로 내림차순 정렬
    sorted_items = sorted(items, key=len, reverse=True)
    result = []

    for i, item in enumerate(sorted_items):
        is_substring = False
        for j, other_item in enumerate(sorted_items):
            if i != j and item in other_item:
                is_substring = True
                break
        if not is_substring:
            result.append(item)

    return result


def extract_middle_line(text):
    '''
    주변명소 답을 리턴할때 장소명만 리턴하는 함수
    특수문자로만 이루어진 경우 원본 text를 반환
    '''
    lines = text.split('\n')

    def contains_only_special_chars(s):
        # 문자열에서 특수문자를 제외한 모든 문자 제거
        import re
        # \w: 단어 문자(알파벳, 숫자, 언더스코어)
        # \s: 공백 문자
        # 한글 포함
        cleaned = re.sub(r'[^\w\s가-힣]', '', s.strip())
        # cleaned가 비어있으면 특수문자만 포함된 것
        return len(cleaned) == 0

    if len(lines) == 3:
        middle_line = lines[1].strip()
        return text if contains_only_special_chars(middle_line) else middle_line
    elif len(lines) == 2:
        first_line = lines[0].strip()
        return text if contains_only_special_chars(first_line) else first_line
    else:
        return text


async def find_Answer_From_CollectedData(chatID, userID, message_str, isTelegram=True):
    '''
    수집된 데이터에서 정답을 검색하는 함수
    chatID : chatID
    userID : 사용자 ID
    message_str : 메시지 원문
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo

    async def send_find_answer():
        '''
        검색된 답을 알려주는 함수
        '''
        nonlocal chatID, key, find_answer_list, leftSide, leftSideAll, rightSide, rightSideAll, bothSideAll, isAllLetter

        isSendAnswer = False
        cnt = 1
        send_mesaage_list = []
        send_reaction_list = []
        for find_answer in list(dict.fromkeys(find_answer_list)):
            # 띄어쓰기가 중복해서 있는 경우 한개로 변경
            # find_answer_normalize = normalize_spaces(find_answer.strip())
            isExistAnswer = False
            if isAllLetter:
                find_answer = extract_middle_line(find_answer)
            find_answer_normalize = find_answer.strip()

            # 검색어가 중간에 있는 경우 길이 제한을 초과하면 정답알림 안함
            if not (leftSide or rightSide or bothSideAll):
                if len(find_answer_normalize) > dataInfo.maxAnswerLen:
                    continue

            # 한쪽방향 열린검색의 경우 문장내 검색이면 길이제한 갯수만큼 잘라서 보여줌
            if leftSide and not leftSideAll:
                # 왼쪽열림 검색이면서 문장내 검색이면 길이제한 만큼 잘라서 보여줌
                if len(find_answer_normalize) > dataInfo.maxAnswerLen:
                    find_answer_normalize = find_answer_normalize[-dataInfo.maxAnswerLen:]
            elif rightSide and not rightSideAll:
                # 오른쪽열림 검색이면서 문장내 검색이면 길이제한 만큼 잘라서 보여줌
                if len(find_answer_normalize) > dataInfo.maxAnswerLen:
                    find_answer_normalize = find_answer_normalize[:dataInfo.maxAnswerLen]

            # 이미 검색결과로 알린 값과 동일하면 패스
            if find_answer_normalize in send_mesaage_list:
                continue
            send_mesaage_list.append(find_answer_normalize)

            # 정답알림 조건을 만족하는지 확인
            matching_items = [
                item for item in dataInfo.answerInfo[key]
                if (item == find_answer_normalize or
                    item.replace(" ", "") == find_answer_normalize.replace(" ", "") or
                    item == remove_special_chars_ends(find_answer_normalize) or
                    item in find_answer_normalize)
            ]
            # matching_items = [item for item in dataInfo.answerInfo[key]if item in find_answer_normalize or item.replace(" ", "") in find_answer_normalize.replace(" ", "")]
            # matching_items = [item for item in dataInfo.answerInfo[key] if item in find_answer_normalize]

            # 부분 문자열 제거
            filtered_items = remove_substrings(matching_items)

            # 기출문제 답이 포함되었는지 확인
            isExistAnswer = bool(filtered_items)

            # 기출문제 답이 포함되지 않았고, 최대허용갯수를 초과한 경우 건너뛰기
            if not isExistAnswer and cnt > dataInfo.maxPatternCnt:
                continue

            if isExistAnswer:
                if isTelegram:
                    sendResult = await telegramInfo.botInfo.bot.send_message(chatID, find_answer_normalize, disable_notification=True)

                if find_answer_normalize in filtered_items:
                    # 기출문제와 정확히 일치하는 경우
                    send_reaction_list.append(find_answer_normalize)
                    if isTelegram:
                        asyncio.create_task(
                            sendResult.set_reaction(reaction='👌'))
                    else:
                        print(find_answer_normalize + ' 👌')
                else:
                    # 기출문제와 부분일치하는 경우
                    isConsolePrint = False
                    for each_items in filtered_items:
                        # 이미 일치를 알렸으면 pass
                        if each_items in send_reaction_list:
                            continue
                        if each_items != remove_special_chars_ends(find_answer_normalize) and \
                           each_items.replace(" ", "") != find_answer_normalize.replace(" ", "") and \
                           (len(find_answer_normalize) < len(each_items) + dataInfo.diffLen and not isAllLetter):
                            continue
                        send_reaction_list.append(each_items)
                        if isTelegram:
                            asyncio.create_task(
                                sendResult.reply_text(each_items, do_quote=True))
                        else:
                            print(find_answer_normalize + ' → ' + each_items)
                            isConsolePrint = True

                if not (isTelegram or isConsolePrint):
                    # 콘솔검색이면서 부분일치를 알리지 않은 경우
                    print(find_answer_normalize)
            else:
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, find_answer_normalize, disable_notification=True))
                else:
                    print(find_answer_normalize)

            isSendAnswer = True
            cnt += 1
        return isSendAnswer

    try:
        key = dataInfo.userInfo[userID]['title']
        leftSide = message_str.startswith('*')
        leftSideAll = message_str.startswith('**')
        rightSide = message_str.endswith('*')
        rightSideAll = message_str.endswith('**')
        bothSideAll = '**' in message_str
        isAllLetter = is_only_consonants(
            message_str.replace('*', '').replace(' ', ''))

        if isAllLetter:
            message_str = convertToInitialLetters(message_str)

        if key not in dataInfo.answerInfo:
            # 찾고자 하는 문제를 검색하지 않은 경우
            msg = f'{key} 라는 문제가 없습니다. 정답을 찾고 싶은 문제를 정확하게 입력하거나 번호를 선택하세요! 😱'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
        elif 'smartstore.naver.com' in dataInfo.answerInfo[key][0] or 'brand.naver.com' in dataInfo.answerInfo[key][0]:
            # 스마트스토어 정답찾기
            store_url = dataInfo.answerInfo[key][0]
            # 스마트스토어 정답찾기
            msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 검색합니다. 🔍'
            if isTelegram:
                await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
                # await asyncio.sleep(dataInfo.sendInterval)
            else:
                print(msg)

            if store_url in dataInfo.naverBuf:
                find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                           dataInfo.naverBuf[store_url], message_str)
            else:
                # 이미 리프레시 대기열에 있는지 확인
                if store_url in dataInfo.refresh_list:
                    msg = f"{key} 문제는 로봇이 정보수집중 입니다. {dataInfo.refresh_buf[store_url]['remaining_time'] if store_url in dataInfo.refresh_buf else '잠시 후'} 에 다시 검색하세요. 🚧"
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
                    return

                # 리프레시 대기열에 추가
                async with dataInfo.refresh_list_lock:
                    dataInfo.refresh_list[store_url] = dict()
                    dataInfo.refresh_list[store_url]['title'] = key
                    dataInfo.refresh_list[store_url]['PageCnt'] = dataInfo.maxPageCnt

                find_answer_list = await get_store_answer(
                    store_url, dataInfo.maxPageCnt, dataInfo.naverInterval, message_str)

                # 리프레시 대기열에서 제거
                async with dataInfo.refresh_list_lock:
                    del dataInfo.refresh_list[store_url]

            if not bool(find_answer_list):
                msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 찾지 못했습니다. 😱'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                    # await asyncio.sleep(dataInfo.sendInterval)
                else:
                    print(msg)
            else:
                # 일치하는 검색어 알림
                isSendAnswer = await send_find_answer()
                if not isSendAnswer:
                    msg = f'{key} 문제에서 {message_str} 과 일치하는 {dataInfo.maxAnswerLen} 글자 이하의 단어를 찾지 못했습니다. 😨'
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
        elif 'place.naver.com' in dataInfo.answerInfo[key][0]:
            place_url = dataInfo.answerInfo[key][0]
            # place 정답찾기
            msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 검색합니다. 🔍'
            if isTelegram:
                await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
                # await asyncio.sleep(dataInfo.sendInterval)
            else:
                print(msg)

            if place_url in dataInfo.naverBuf:
                find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                           dataInfo.naverBuf[place_url], message_str)
            else:
                # 이미 리프레시 대기열에 있는지 확인
                if place_url in dataInfo.refresh_list:
                    msg = f"{key} 문제는 로봇이 정보수집중 입니다. {dataInfo.refresh_buf[place_url]['remaining_time'] if place_url in dataInfo.refresh_buf else '잠시'} 후에 다시 검색하세요. 🚧"
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
                    return

                # 리프레시 대기열에 추가
                async with dataInfo.refresh_list_lock:
                    dataInfo.refresh_list[place_url] = dict()
                    dataInfo.refresh_list[place_url]['title'] = key
                    dataInfo.refresh_list[place_url]['PageCnt'] = dataInfo.maxPageCnt

                find_answer_list = await get_place_answer(
                    place_url, dataInfo.maxPageCnt, dataInfo.naverInterval, message_str)

                # 리프레시 대기열에서 제거
                async with dataInfo.refresh_list_lock:
                    del dataInfo.refresh_list[place_url]

            if not bool(find_answer_list):
                msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 찾지 못했습니다. 😱'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                    # await asyncio.sleep(dataInfo.sendInterval)
                else:
                    print(msg)
            else:
                # 일치하는 검색어 알림
                isSendAnswer = await send_find_answer()
                if not isSendAnswer:
                    msg = f'{key} 문제에서 {message_str} 과 일치하는 {dataInfo.maxAnswerLen} 글자 이하의 단어를 찾지 못했습니다. 😨'
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
        elif 'place.map.kakao.com' in dataInfo.answerInfo[key][0]:
            place_url = dataInfo.answerInfo[key][0]
            # place 정답찾기
            msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 검색합니다. 🔍'
            if isTelegram:
                await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
                # await asyncio.sleep(dataInfo.sendInterval)
            else:
                print(msg)

            if place_url in dataInfo.naverBuf:
                find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                           dataInfo.naverBuf[place_url], message_str)
            else:
                # 이미 리프레시 대기열에 있는지 확인
                if place_url in dataInfo.refresh_list:
                    msg = f"{key} 문제는 로봇이 정보수집중 입니다. {dataInfo.refresh_buf[place_url]['remaining_time'] if place_url in dataInfo.refresh_buf else '잠시'} 후에 다시 검색하세요. 🚧"
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
                    return

                # 리프레시 대기열에 추가
                async with dataInfo.refresh_list_lock:
                    dataInfo.refresh_list[place_url] = dict()
                    dataInfo.refresh_list[place_url]['title'] = key
                    dataInfo.refresh_list[place_url]['PageCnt'] = dataInfo.maxPageCnt

                find_answer_list = await get_kakao_place_answer(
                    place_url, dataInfo.maxPageCnt, dataInfo.naverInterval, message_str)

                # 리프레시 대기열에서 제거
                async with dataInfo.refresh_list_lock:
                    del dataInfo.refresh_list[place_url]

            if not bool(find_answer_list):
                msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 찾지 못했습니다. 😱'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                    # await asyncio.sleep(dataInfo.sendInterval)
                else:
                    print(msg)
            else:
                # 일치하는 검색어 알림
                isSendAnswer = await send_find_answer()
                if not isSendAnswer:
                    msg = f'{key} 문제에서 {message_str} 과 일치하는 {dataInfo.maxAnswerLen} 글자 이하의 단어를 찾지 못했습니다. 😨'
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
        elif dataInfo.answerInfo[key][0] in dataInfo.naverBuf:
            page_url = dataInfo.answerInfo[key][0]
            # place 정답찾기
            msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 검색합니다. 🔍'
            if isTelegram:
                await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
                # await asyncio.sleep(dataInfo.sendInterval)
            else:
                print(msg)
            find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                       dataInfo.naverBuf[page_url], message_str)
            if not bool(find_answer_list):
                msg = f'{key} 문제에서 {message_str} 과 일치하는 단어를 찾지 못했습니다. 😱'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                    # await asyncio.sleep(dataInfo.sendInterval)
                else:
                    print(msg)
            else:
                # 일치하는 검색어 알림
                isSendAnswer = await send_find_answer()
                if not isSendAnswer:
                    msg = f'{key} 문제에서 {message_str} 과 일치하는 {dataInfo.maxAnswerLen} 글자 이하의 단어를 찾지 못했습니다. 😨'
                    if isTelegram:
                        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                            chatID, msg, disable_notification=True))
                    else:
                        print(msg)
        else:
            msg = f'{key} 는 단어검색을 할 수 없습니다. 관리자에게 문의하세요. 📞'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return


async def push_Next_AllCollected(chatID, userID, isTelegram=True):
    '''
    사용자가 계속 문제를 확인한다고 한 경우 다음 문제 리스트를 출력하는 함수
    '''
    start_idx = dataInfo.userInfo[userID]['nextAllCollectedIndex']
    for idx in range(start_idx, len(dataInfo.userInfo[userID]['allCollected'])):
        # 최대 문제알림 갯수를 넘어가면 계속 문제를 확인할껀지 확인
        if (idx - start_idx) >= dataInfo.maxPushCnt:
            async with dataInfo.userInfo_lock:
                dataInfo.userInfo[userID]['nextAllCollectedIndex'] = idx
            msg = '계속 문제를 확인하려면 "네" 를 입력하세요.. 😃'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
            break

        row = dataInfo.userInfo[userID]['allCollected'][idx]
        for key in row:
            # 정답 제목
            if isTelegram:
                await telegramInfo.botInfo.bot.send_message(chatID, f'{key} 답 🎯', disable_notification=True)
                await telegramInfo.botInfo.bot.send_message(chatID, row[key]['url'], disable_notification=True, link_preview_options={
                    'url': row[key]['url'],
                    'prefer_small_media': dataInfo.userInfo[userID].get("image", True),
                    'show_above_text': False
                }
                )
            else:
                print(f'{key} 답 🎯')
                print(row[key]['url'])
            # 정답
            submatchAnswerDict = {}
            for answer in row[key]['answer']:
                isExistAnswer = False
                # 정답알림 조건을 만족하는지 확인
                matching_items = [
                    item for item in dataInfo.answerInfo[key]
                    if (item == answer or
                        item.replace(" ", "") == answer.replace(" ", "") or
                        item == remove_special_chars_ends(answer) or
                        item in answer)
                ]
                # 부분 일치 문자열 제거
                filtered_items = remove_substrings(matching_items)

                if bool(filtered_items):
                    # 기출문제 답이 포함된 검색결과
                    isExistAnswer = True

                if isExistAnswer:
                    if isTelegram:
                        sendResult = await telegramInfo.botInfo.bot.send_message(chatID, answer, disable_notification=True)

                    if answer in filtered_items:
                        if isTelegram:
                            asyncio.create_task(
                                sendResult.set_reaction(reaction='👌'))
                        else:
                            print(answer + ' 👌')
                    else:
                        # 기출문제와 부분일치하는 경우
                        for each_items in filtered_items:
                            if each_items != remove_special_chars_ends(answer) and \
                                    each_items.replace(" ", "") != answer.replace(" ", "") and \
                                    each_items not in answer.split('\n') and \
                                    len(answer) < len(each_items) + dataInfo.diffLen:
                                continue
                            submatchAnswerDict.update({each_items: key})
                            if isTelegram:
                                asyncio.create_task(
                                    sendResult.reply_text(each_items, do_quote=True))
                            else:
                                print(answer + ' → ' + each_items)
                else:
                    if isTelegram:
                        sendResult = await telegramInfo.botInfo.bot.send_message(chatID, answer, disable_notification=True)
                    else:
                        print(answer)
            # 관리자는 정답후보정보에 기출문제와 부분일치하는 정보도 업데이트
            if userID in dataInfo.answerManageMember:
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_answer_info'].update(
                        submatchAnswerDict)
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)
    else:
        async with dataInfo.userInfo_lock:
            dataInfo.userInfo[userID]['nextAllCollectedIndex'] = 0

    return


async def find_Answer_From_AllCollected(chatID, userID, message_str, token='@', isTelegram=True):
    '''
    모든문제 정답에서 검색하는 함수
    chatID : chatID
    userID : 사용자 ID
    message_str : 메시지 원문
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo

    async def find_AllCollected_answer():
        '''
        검색된 답을 알려주는 함수
        '''
        nonlocal chatID, key, find_all_answer, leftSide, leftSideAll, rightSide, rightSideAll, bothSideAll, isAllLetter
        dataInfo.userInfo[userID]['allCollected'] = list()
        for key in find_all_answer.keys():
            find_past_answer = []
            for find_answer in list(dict.fromkeys(find_all_answer[key]['answer'])):
                if isAllLetter:
                    find_answer = extract_middle_line(find_answer)
                find_answer_normalize = find_answer.strip()

                # 검색어가 중간에 있는 경우 길이 제한을 초과하면 정답알림 안함
                if not (leftSide or rightSide or bothSideAll):
                    if len(find_answer_normalize) > dataInfo.maxAnswerLen:
                        continue

                # 한쪽방향 열린검색의 경우 문장내 검색이면 길이제한 갯수만큼 잘라서 보여줌
                if leftSide and not leftSideAll:
                    # 왼쪽열림 검색이면서 문장내 검색이면 길이제한 만큼 잘라서 보여줌
                    if len(find_answer_normalize) > dataInfo.maxAnswerLen:
                        find_answer_normalize = find_answer_normalize[-dataInfo.maxAnswerLen:]
                elif rightSide and not rightSideAll:
                    # 오른쪽열림 검색이면서 문장내 검색이면 길이제한 만큼 잘라서 보여줌
                    if len(find_answer_normalize) > dataInfo.maxAnswerLen:
                        find_answer_normalize = find_answer_normalize[:dataInfo.maxAnswerLen]

                # 이미 검색결과로 알린 값과 동일하면 패스
                if find_answer_normalize in find_past_answer:
                    continue
                find_past_answer.append(find_answer_normalize)

            # 일치하는 정답이 없으면 pass
            if not bool(find_past_answer):
                continue

            # 정답정보 생성
            answer_info = dict()
            answer_info[key] = {
                'url': find_all_answer[key]['url'],
                'answer': find_past_answer
            }
            dataInfo.userInfo[userID]['allCollected'].append(answer_info)
        return
    try:
        key = dataInfo.userInfo[userID]['title']
        leftSide = message_str.startswith(token)
        leftSideAll = message_str.startswith(token+token)
        rightSide = message_str.endswith(token)
        rightSideAll = message_str.endswith(token+token)
        bothSideAll = token+token in message_str
        isAllLetter = is_only_consonants(
            message_str.replace(token, '').replace(' ', ''))

        if isAllLetter:
            message_str = convertToInitialLetters(message_str)

        # @검색은 최소 조건을 만족하는지 확인
        # if token == '@':
        #     message_str_edit = re.sub(r'{token}{2,}', token, message_str)
        #     for sentence in message_str_edit.split(token):
        #         if ' ' in sentence:
        #             break
        #     else:
        #         msg = f'@ 검색을 하려면 앞 혹은 뒤에 최소한 2개 이상 단어 혹은 단어의 일부를 입력하세요. 😅'
        #         if isTelegram:
        #             asyncio.create_task(telegramInfo.botInfo.bot.send_message(
        #                 chatID, msg, disable_notification=True))
        #             # await asyncio.sleep(dataInfo.sendInterval)
        #         else:
        #             print(msg)
        #         return

        find_all_answer = dict()
        chunk_size = 50  # 한 번에 처리할 키의 수

        # 키 리스트를 chunk로 나누기
        keys = list(dataInfo.answerInfo.keys())
        key_chunks = [keys[i:i + chunk_size]
                      for i in range(0, len(keys), chunk_size)]

        async def process_single_key(key):
            """단일 키를 처리하는 비동기 함수"""
            # nonList 를 설정하고 * 검색한 경우
            if token == '*' and key not in dataInfo.userInfo[userID]['titleList']:
                return None
            if 'smartstore.naver.com' in dataInfo.answerInfo[key][0] or 'brand.naver.com' in dataInfo.answerInfo[key][0]:
                # 스마트스토어 정답찾기
                store_url = dataInfo.answerInfo[key][0]
                if store_url in dataInfo.naverBuf:
                    find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                               dataInfo.naverBuf[store_url], message_str, token)
                else:
                    return None
                if bool(find_answer_list):
                    return (key, {'url': store_url, 'answer': find_answer_list})
            elif 'place.naver.com' in dataInfo.answerInfo[key][0]:
                place_url = dataInfo.answerInfo[key][0]
                if place_url in dataInfo.naverBuf:
                    find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                               dataInfo.naverBuf[place_url], message_str, token)
                else:
                    return None
                if bool(find_answer_list):
                    return (key, {'url': place_url, 'answer': find_answer_list})
            elif 'place.map.kakao.com' in dataInfo.answerInfo[key][0]:
                place_url = dataInfo.answerInfo[key][0]
                if place_url in dataInfo.naverBuf:
                    find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                               dataInfo.naverBuf[place_url], message_str, token)
                else:
                    return None
                if bool(find_answer_list):
                    return (key, {'url': place_url, 'answer': find_answer_list})
            elif dataInfo.answerInfo[key][0] in dataInfo.naverBuf:
                page_url = dataInfo.answerInfo[key][0]
                find_answer_list = await asyncio.to_thread(find_pattern_in_list,
                                                           dataInfo.naverBuf[page_url], message_str, token)
                if bool(find_answer_list):
                    return (key, {'url': page_url, 'answer': find_answer_list})
            return None

        # chunk 단위로 처리
        for chunk in key_chunks:
            # 각 chunk 내의 키들을 동시에 처리
            tasks = [process_single_key(key) for key in chunk]
            results = await asyncio.gather(*tasks)

            # 결과 취합
            for result in results:
                if result:
                    key, value = result
                    find_all_answer[key] = value

            # chunk 처리 후 다른 태스크에 기회 부여
            await asyncio.sleep(0)

        if not bool(find_all_answer):
            msg = f'수집된 정보에서 {message_str} 에 맞는 문장을 찾지 못했습니다. 😱'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
                # await asyncio.sleep(dataInfo.sendInterval)
            else:
                print(msg)
            return

        # 기출문제 정답 찾기
        await find_AllCollected_answer()

        if not bool(dataInfo.userInfo[userID]['allCollected']):
            msg = f'{message_str} 에 해당하는 답을 찾지 못했습니다. 😔'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
                # await asyncio.sleep(dataInfo.sendInterval)
            else:
                print(msg)
            return

        # 관리자는 정답입력 제목정보 초기화 및 정답후보정보 저장
        if userID in dataInfo.answerManageMember:
            dataInfo.answerKey[f'{userID}_title'] = None
            dataInfo.answerKey[f'{userID}_title_buf'] = None
            answerDict = {}
            for answer_info in dataInfo.userInfo[userID]['allCollected']:
                # answer_info의 첫 번째 키를 가져옵니다
                first_key = next(iter(answer_info))
                # answer_info에서 'answer' 리스트를 가져옵니다
                find_past_answer = answer_info[first_key]['answer']
                answerDict.update(
                    {item: first_key for item in find_past_answer})
            async with dataInfo.answerKey_lock:
                dataInfo.answerKey[f'{userID}_answer_info'].update(answerDict)
                await answerKeyInfo.save_pickle(dataInfo.answerKey)

        # 찾은 정답 알림
        for idx, row in enumerate(dataInfo.userInfo[userID]['allCollected']):
            # 최대 문제알림 갯수를 넘어가면 계속 문제를 확인할껀지 확인
            if idx >= dataInfo.maxPushCnt:
                async with dataInfo.userInfo_lock:
                    dataInfo.userInfo[userID]['nextAllCollectedIndex'] = idx
                msg = '계속 문제를 확인하려면 "네" 를 입력하세요 😃'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
                break

            for key in row:
                # 정답 제목
                if isTelegram:
                    await telegramInfo.botInfo.bot.send_message(chatID, f'{key} 답 🎯', disable_notification=True)
                    await telegramInfo.botInfo.bot.send_message(chatID, row[key]['url'], disable_notification=True, link_preview_options={
                        'url': row[key]['url'],
                        'prefer_small_media': dataInfo.userInfo[userID].get("image", True),
                        'show_above_text': False
                    }
                    )
                else:
                    print(f'{key} 답 🎯')
                    print(row[key]['url'])

                # 정답
                submatchAnswerDict = {}
                cnt = 1
                for answer in row[key]['answer']:
                    isExistAnswer = False
                    # 정답알림 조건을 만족하는지 확인
                    matching_items = [
                        item for item in dataInfo.answerInfo[key]
                        if (item == answer or
                            item.replace(" ", "") == answer.replace(" ", "") or
                            item == remove_special_chars_ends(answer) or
                            item in answer)
                    ]
                    # 부분일치 문자열 제거
                    filtered_items = remove_substrings(matching_items)

                    # 기출문제 답이 포함되었는지 확인
                    isExistAnswer = bool(filtered_items)

                    # 기출문제 답이 포함되지 않았고, 최대허용갯수를 초과한 경우 건너뛰기
                    if not isExistAnswer and cnt > dataInfo.maxPatternCnt:
                        continue

                    if isExistAnswer:
                        if isTelegram:
                            sendResult = await telegramInfo.botInfo.bot.send_message(chatID, answer, disable_notification=True)

                        if answer in filtered_items:
                            if isTelegram:
                                asyncio.create_task(
                                    sendResult.set_reaction(reaction='👌'))
                            else:
                                print(answer + ' 👌')
                        else:
                            # 기출문제와 부분일치하는 경우
                            isConsolePrint = False
                            for each_items in filtered_items:
                                if each_items != remove_special_chars_ends(answer) and \
                                        each_items.replace(" ", "") != answer.replace(" ", "") and \
                                        (len(answer) < len(each_items) + dataInfo.diffLen and not isAllLetter):
                                    continue
                                submatchAnswerDict.update({each_items: key})
                                if isTelegram:
                                    asyncio.create_task(
                                        sendResult.reply_text(each_items, do_quote=True))
                                else:
                                    print(answer + ' → ' + each_items)
                                    isConsolePrint = True

                            if not (isTelegram or isConsolePrint):
                                # 콘솔검색이면서 부분일치를 알리지 않은 경우
                                print(answer)
                    else:
                        if isTelegram:
                            sendResult = await telegramInfo.botInfo.bot.send_message(chatID, answer, disable_notification=True)
                        else:
                            print(answer)
                    cnt += 1
                # 관리자는 정답후보정보에 기출문제와 부분일치하는 정보도 업데이트
                if userID in dataInfo.answerManageMember:
                    async with dataInfo.answerKey_lock:
                        dataInfo.answerKey[f'{userID}_answer_info'].update(
                            submatchAnswerDict)
                        await answerKeyInfo.save_pickle(dataInfo.answerKey)
        else:
            async with dataInfo.userInfo_lock:
                dataInfo.userInfo[userID]['nextAllCollectedIndex'] = 0

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return


async def push_Next_UserSearch(chatID, userID, isTelegram=True):
    '''
    사용자가 계속 문제를 확인한다고 한 경우 다음 문제 리스트를 출력하는 함수
    '''
    start_idx = dataInfo.userInfo[userID]['nextPushIndex']
    if not dataInfo.userInfo[userID].get('nonList', False):
        for idx in range(start_idx, len(dataInfo.userInfo[userID]['answer'])):
            # 최대 문제알림 갯수를 넘어가면 계속 문제를 확인할껀지 확인
            if (idx - start_idx) >= dataInfo.maxPushCnt:
                async with dataInfo.userInfo_lock:
                    dataInfo.userInfo[userID]['nextPushIndex'] = idx
                msg = '계속 문제를 확인하려면 "네" 를 입력하시고, 아니면 답을 보고 싶은 문제 번호를 입력하세요.. 😃'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
                break
            row = dataInfo.userInfo[userID]['answer'][idx]
            msg = f'{idx+1}.{row[0]}'
            # URL 이 있으면 추가
            if len(row) > 1 and 'http' in row[1] and not contains_any_except_link(row[1], dataInfo.exceptLink):
                msg = msg + '\n' + f'{row[1]}'
                if isTelegram:
                    await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True, link_preview_options={
                        'url': row[1],
                        'prefer_small_media': dataInfo.userInfo[userID].get("image", True),
                        'show_above_text': False
                    }
                    )
                else:
                    print(msg)
            else:
                if isTelegram:
                    await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
                else:
                    print(msg)
            # await asyncio.sleep(dataInfo.sendInterval)
        else:
            async with dataInfo.userInfo_lock:
                dataInfo.userInfo[userID]['nextPushIndex'] = 0
            msg = f'답을 보고 싶은 문제 번호를 입력하세요.. 😃'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)
    else:
        # 문제를 개별적으로 보고 싶지 않은 user는 한번에 모든 문제와 정답을 보여줌
        for idx in range(start_idx, len(dataInfo.userInfo[userID]['answer'])):
            # 최대 문제알림 갯수를 넘어가면 계속 문제를 확인할껀지 확인
            if (idx - start_idx) >= dataInfo.maxPushCnt:
                async with dataInfo.userInfo_lock:
                    dataInfo.userInfo[userID]['nextPushIndex'] = idx
                if userID in dataInfo.premiumMember:
                    msg = '계속 문제를 확인하려면 "네" 를 입력하시고, 필요하면 바로 "*" 검색하세요... 😃'
                else:
                    msg = '계속 문제를 확인하려면 "네" 를 입력하세요.. 😃'
                if isTelegram:
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        chatID, msg, disable_notification=True))
                else:
                    print(msg)
                break
            row = dataInfo.userInfo[userID]['answer'][idx]
            msg = f'{idx+1}.{row[0]}'
            if isTelegram:
                await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
            else:
                print(msg)
            for line in row[1:]:
                if "http" not in line:
                    if isTelegram:
                        await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True)
                    else:
                        print(line)
                elif contains_any_except_link(line, dataInfo.exceptLink):
                    if isTelegram:
                        await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True, disable_web_page_preview=True)
                    else:
                        print(line)
                else:
                    if isTelegram:
                        await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True, link_preview_options={
                            'url': line,
                            'prefer_small_media': dataInfo.userInfo[userID].get("image", True),
                            'show_above_text': True
                        }
                        )
                    else:
                        print(line)
        else:
            async with dataInfo.userInfo_lock:
                dataInfo.userInfo[userID]['nextPushIndex'] = 0
        return


def is_only_consonants(text):
    # 모든 한글 자음과 알파벳, 숫자, 하이픈만 포함하는지 확인
    for ch in text:
        if not (ch in 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎㄳㄵㄶㄺㄻㄼㄽㄾㄿㅀㅄ' or ch.isascii() and ch.isalpha() or ch.isdigit() or ch == '-'):
            return False
    return True


async def find_Question_From_UserSearch(chatID, userID, message_str, num_items, isURL=False, isTelegram=True):
    '''
    사용자가 입력에 맞는 문제를 찾는 함수
    chatID : chatID
    userID : 사용자 ID
    message_edit : 사용자가 입력한 문자
    message_edit_words : 정답을 검색할 문자
    num_items : 가져올 정답 갯수
    isURL : url 링크만 찾는지?
    isTelegram  telegram 모드 or console 모드
    '''
    global dataInfo, telegramInfo

    try:
        isPastPapers = False
        # 검색어 분리
        message_edit_words = split_strings(remove_digits(message_str.lower()))

        result = []
        # nonList 설정시 제목정보를 저장
        keyBuf = []
        answerDict = {}
        for key in dataInfo.answerInfo:
            # 문제제목에 초성정보 추가
            key_edit = key + convertToInitialLetters(key)
            if all(word.strip() in key_edit for word in message_edit_words):  # 모든 단어가 key에 포함되어 있는지 확인
                isPastPapers = True
                answerList = []
                answerList.append(f"{key} 답 💡")

                # nonList 설정시 제목정보를 저장
                keyBuf.append(key)

                # 정답을 가져올 갯수 확인
                item_count = num_items
                if num_items > len(dataInfo.answerInfo[key]):
                    item_count = len(dataInfo.answerInfo[key])

                added_count = 0
                for value in reversed(dataInfo.answerInfo[key]):
                    # smartstore 링크가 MerchantNo 가 포함된 리스트면 url 값만 가져옴
                    if isinstance(value, list):
                        value = value[0]
                    if isURL and ("http" not in value or contains_any_except_link(value, dataInfo.exceptLink)):
                        # URL 링크만 리턴해야할 때, http 가 없거나 제외해야하는 링크인 경우 pass
                        continue
                    if 'http' in value and not contains_any_except_link(value, dataInfo.exceptLink):
                        # 'http'가 포함된 아이템은 answerList의 가장 앞에 추가합니다.
                        answerList.insert(1, value)
                    elif added_count >= item_count:
                        # 정답확인 갯수를 초과하면 pass
                        continue
                    else:
                        # 정답입력을 위해 답과 제목 정보 저장
                        answerDict[value] = key
                        # 'http'가 포함되지 않은 아이템은 answerList의 끝에 추가합니다.
                        answerList.append(value)
                        added_count = added_count + 1
                if answerList:
                    result.append(answerList)

        if isPastPapers:
            # 검색어와 일치하는 문제가 1개 인 경우
            if len(result) == 1:
                # 프리미엄회원인 경우
                if userID in dataInfo.premiumMember:
                    async with dataInfo.userInfo_lock:
                        # 정답 찾기를 할지 모르니 일단 저장
                        dataInfo.userInfo[userID]['title'] = result[0][0][:-4]
                        dataInfo.userInfo[userID]['titleList'] = keyBuf
                # 관리자는 정답후보로도 저장
                if userID in dataInfo.answerManageMember:
                    async with dataInfo.answerKey_lock:
                        dataInfo.answerKey[f'{userID}_title_buf'] = dataInfo.userInfo[userID]['title']
                        await answerKeyInfo.save_pickle(dataInfo.answerKey)

                # 검색과 일치하는 문제와 정답 알림
                for line in result[0]:
                    if "http" not in line:
                        if isTelegram:
                            await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True)
                        else:
                            print(line)
                    elif contains_any_except_link(line, dataInfo.exceptLink):
                        if isTelegram:
                            await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True, disable_web_page_preview=True)
                        else:
                            print(line)
                    else:
                        if isTelegram:
                            # 정답 사이트 포맷 설정
                            await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True, link_preview_options={
                                'url': line,
                                'prefer_small_media': dataInfo.userInfo[userID].get("image", True),
                                'show_above_text': True
                            }
                            )
                        else:
                            print(line)
                    # if isTelegram:
                    #     await asyncio.sleep(dataInfo.sendInterval)
            else:
                # 검색어와 일치하는 문제가 2개 이상인 경우
                async with dataInfo.userInfo_lock:
                    # 검색어와 일치하는 문제와 정답을 버퍼에 저장
                    dataInfo.userInfo[userID]['answer'] = result
                    dataInfo.userInfo[userID]['nextPushIndex'] = 0
                    dataInfo.userInfo[userID]['titleList'] = keyBuf
                    await userInfo.save_pickle(dataInfo.userInfo)

                # 관리자는 정답후보로도 저장
                if userID in dataInfo.answerManageMember:
                    async with dataInfo.answerKey_lock:
                        dataInfo.answerKey[f'{userID}_title'] = None
                        dataInfo.answerKey[f'{userID}_title_buf'] = None
                        dataInfo.answerKey[f'{userID}_answer_info'] = answerDict
                        await answerKeyInfo.save_pickle(dataInfo.answerKey)

                # 정답을 확인하고 싶은 문제를 선택할 수 있도록 검색어와 일치하는 문제 리스트를 보여줌
                if not dataInfo.userInfo[userID].get('nonList', False):
                    # 일치하는 문제 리스트를 보여주는 경우
                    for idx, row in enumerate(result):
                        # 최대 문제알림 갯수를 넘어가면 계속 문제를 확인할껀지 확인
                        if idx >= dataInfo.maxPushCnt:
                            async with dataInfo.userInfo_lock:
                                dataInfo.userInfo[userID]['nextPushIndex'] = idx
                            msg = '계속 문제를 확인하려면 "네" 를 입력하시고, 아니면 답을 보고 싶은 문제 번호를 입력하세요.. 😃'
                            if isTelegram:
                                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                    chatID, msg, disable_notification=True))
                            else:
                                print(msg)
                            break
                        msg = f'{idx+1}.{row[0]}'
                        # URL 이 있으면 추가
                        if len(row) > 1 and 'http' in row[1] and not contains_any_except_link(row[1], dataInfo.exceptLink):
                            msg = msg + '\n' + f'{row[1]}'
                            if isTelegram:
                                await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True, link_preview_options={
                                    'url': row[1],
                                    'prefer_small_media': dataInfo.userInfo[userID].get("image", True),
                                    'show_above_text': False
                                }
                                )
                            else:
                                print(msg)
                        else:
                            if isTelegram:
                                await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
                            else:
                                print(msg)
                        # await asyncio.sleep(dataInfo.sendInterval)
                    else:
                        async with dataInfo.userInfo_lock:
                            dataInfo.userInfo[userID]['nextPushIndex'] = 0
                        msg = f'답을 보고 싶은 문제 번호를 입력하세요.. 😃'
                        if isTelegram:
                            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                chatID, msg, disable_notification=True))
                        else:
                            print(msg)
                else:
                    # 문제를 개별적으로 보고 싶지 않은 user는 한번에 모든 문제와 정답을 보여줌
                    for idx, row in enumerate(result):
                        # 최대 문제알림 갯수를 넘어가면 계속 문제를 확인할껀지 확인
                        if idx >= dataInfo.maxPushCnt:
                            async with dataInfo.userInfo_lock:
                                dataInfo.userInfo[userID]['nextPushIndex'] = idx
                            if userID in dataInfo.premiumMember:
                                msg = '계속 문제를 확인하려면 "네" 를 입력하시고, 필요하면 바로 "*" 검색하세요.. 😃'
                            else:
                                msg = '계속 문제를 확인하려면 "네" 를 입력하세요.. 😃'
                            if isTelegram:
                                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                    chatID, msg, disable_notification=True))
                            else:
                                print(msg)
                            break
                        msg = f'{idx+1}.{row[0]}'
                        if isTelegram:
                            await telegramInfo.botInfo.bot.send_message(chatID, msg, disable_notification=True)
                        else:
                            print(msg)

                        for line in row[1:]:
                            if "http" not in line:
                                if isTelegram:
                                    await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True)
                                else:
                                    print(line)
                            elif contains_any_except_link(line, dataInfo.exceptLink):
                                if isTelegram:
                                    await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True, disable_web_page_preview=True)
                                else:
                                    print(line)
                            else:
                                if isTelegram:
                                    await telegramInfo.botInfo.bot.send_message(chatID, line, disable_notification=True, link_preview_options={
                                        'url': line,
                                        'prefer_small_media': dataInfo.userInfo[userID].get("image", True),
                                        'show_above_text': True
                                    }
                                    )
                                else:
                                    print(line)
                    else:
                        async with dataInfo.userInfo_lock:
                            dataInfo.userInfo[userID]['nextPushIndex'] = 0
                        if userID in dataInfo.premiumMember:
                            if not dataInfo.userInfo[userID].get('nonList', False):
                                msg = f'"*" 검색을 하고 싶다면 문제 번호를 입력하세요.. 😃'
                            else:
                                msg = f'"*" 검색을 하면 검색된 문제에서만 정답을 찾습니다.. 😃'
                            if isTelegram:
                                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                                    chatID, msg, disable_notification=True))
                            else:
                                print(msg)
        else:
            # 검색어와 일치하는 문제를 찾지 못한 경우
            msg = f'{message_str} 가 들어간 문제의 {"답" if not isURL else "URL"}을 찾을 수 없습니다. 😱'
            if isTelegram:
                asyncio.create_task(
                    telegramInfo.botInfo.bot.send_message(chatID, msg))
            else:
                print(msg)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return


async def send_reject_message(chatID, userID, username):
    '''
    거절메시지를 보내는 함수
    '''
    global telegramInfo

    msg = f'⛔ 사용권한이 없습니다. ⛔\n' \
        f'관리자에게 문의하세요. 📞'
    asyncio.create_task(telegramInfo.botInfo.bot.send_message(chatID, msg))
    msg = f'{username} ({userID}) 의 요청을 거절했습니다. ⛔'
    asyncio.create_task(writelog(msg, telegram=True))
    return


async def handle_title_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    update : update 객체
    context : context 객체
    '''
    global dataInfo, telegramInfo, userInfo

    try:
        # 새로운 user 이면 info 정보 생성
        if update.message:
            chatID = str(update.message.chat_id)
            userID = str(update.message.from_user.id)
            username = update.message.from_user.full_name
            message_str = update.message.text
            reply_message_str = update.message.reply_to_message.text if update.message.reply_to_message else None
        else:
            chatID = str(update.edited_message.chat_id)
            userID = str(update.edited_message.from_user.id)
            username = update.edited_message.from_user.full_name
            message_str = update.edited_message.text
            reply_message_str = update.edited_message.reply_to_message.text if update.edited_message.reply_to_message else None

        # 멤버가 아니면 대화 거절
        if not check_member(userID):
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        if userID not in dataInfo.userInfo:
            # 신규사용자
            async with dataInfo.userInfo_lock:
                dataInfo.userInfo[userID] = dict()
                dataInfo.userInfo[userID]['username'] = username
                await userInfo.save_pickle(dataInfo.userInfo)
            msg = f'캐시트리봇 입니다. 사용방법은 /help 또는 /h 로 확인하세요.'
            asyncio.create_task(
                telegramInfo.botInfo.bot.send_message(chatID, msg))
            logmsg = f'🔔 {username} ({userID}) 님을 등록했습니다!! 🔔'
            for adminUser in dataInfo.adminMember:
                asyncio.create_task(
                    telegramInfo.botInfo.bot.send_message(adminUser, logmsg))
            print(logmsg)
            asyncio.create_task(writelog(logmsg, True))
        elif username != dataInfo.userInfo[userID].get('username', None):
            # username 업데이트
            async with dataInfo.userInfo_lock:
                oldUsername = dataInfo.userInfo[userID].get('username', None)
                dataInfo.userInfo[userID]['username'] = username
                await userInfo.save_pickle(dataInfo.userInfo)
            logmsg = f'사용자이름 변경 : {oldUsername} → {username} 변경 🔔'
            for adminUser in dataInfo.adminMember:
                asyncio.create_task(
                    telegramInfo.botInfo.bot.send_message(adminUser, logmsg))
            print(logmsg)

        # 정답질문에 대한 답변
        message_edit = message_str.lower()

        # answerInfo 데이터 업데이트
        if userID in dataInfo.adminMember and message_str.startswith(";;"):
            asyncio.create_task(run_admin_command(
                chatID, userID, message_str, message_edit, reply_message_str, isTelegram=True))
            return

        # ;으로 시작하는 질문은 URL 링크만 리턴
        isURL = False
        if message_edit.startswith(";"):
            isURL = True
            message_edit = message_edit[1:]
            # 예약된 정답이 있으면 취소
            if userID in dataInfo.answerManageMember:
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_title'] = None
                    await answerKeyInfo.save_pickle(dataInfo.answerKey)

        if not bool(message_edit):
            # 입력값이 없으면 리턴
            return

        logmsg = f'{username}({userID}): {message_str if not reply_message_str else message_str + " (" + reply_message_str + ")"}'
        print(logmsg)

        asyncio.create_task(writelog(logmsg, False))
        # alert 모드일때는 관리자에게 알림
        for alertUserID in dataInfo.adminMember:
            if dataInfo.answerKey.get(f'{alertUserID}_alert', False) and userID != alertUserID:
                # 현재 시간 가져오기
                current_time = datetime.now()

                # 해당 관리자에 대한 딕셔너리가 없으면 생성
                if alertUserID not in dataInfo.last_alert_time:
                    dataInfo.last_alert_time[alertUserID] = {}

                # 마지막 알림 시간 가져오기
                last_time = dataInfo.last_alert_time[alertUserID].get(userID)

                # 마지막 알림이 없거나 10분 이상 경과했다면 알림 전송
                if last_time is None or (current_time - last_time).total_seconds() >= dataInfo.alert_idle_time:
                    # 알림 전송
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(alertUserID, logmsg))
                    # 마지막 알림 시간 업데이트
                    dataInfo.last_alert_time[alertUserID][userID] = current_time

        # 정답정보 업데이트
        if userID in dataInfo.answerManageMember and '*' not in message_edit:
            update_result = await update_answer_data(chatID, userID, message_str, message_edit, reply_message_str, isTelegram=True)
            if update_result:
                return

        # message_edit가 콜론과 숫자로 구성되어 있는지 확인하고, 해당 숫자를 추출합니다.
        if ':' in message_edit:
            num_items, message_edit = await update_user_items_count(chatID, userID, message_edit, isTelegram=True)
        else:
            num_items = dataInfo.userInfo[userID].get(
                'num_items', dataInfo.maxAnswerCnt)

        if not bool(message_edit):
            # 검색할 문제가 없으면 종료
            return

        # 요청처리
        if is_integer(message_edit):
            # 문제후보 중 하나를 선택한 경우
            asyncio.create_task(get_Answer_For_Selected_Problem(
                chatID, userID, message_edit, isTelegram=True))
            return
        elif dataInfo.userInfo[userID].get('nextAllCollectedIndex', 0) != 0 and message_edit == "네":
            # 기출문제 검색 결과를 계속 출력한다고 한 경우
            asyncio.create_task(push_Next_AllCollected(
                chatID, userID, isTelegram=True))
            return
        elif dataInfo.userInfo[userID].get('nextPushIndex', 0) != 0 and message_edit == "네":
            # 문제 리스트를 계속 출력한다고 한 경우
            asyncio.create_task(push_Next_UserSearch(
                chatID, userID, isTelegram=True))
            return
        elif userID in dataInfo.premiumMember and bool(dataInfo.userInfo[userID].get('title', False)) and '*' in message_edit and message_edit != '*':
            # 프리미엄 멤버이고, 정답 찾기를 위한 제목이 있고, 검색조건인 * 이 있으면 검색 시작
            if not dataInfo.userInfo[userID].get('nonList', False) or len(dataInfo.userInfo[userID]['titleList']) == 1:
                # 정답을 확인하고 싶은 문제를 선택하도록 설정한 경우
                asyncio.create_task(find_Answer_From_CollectedData(
                    chatID, userID, message_str, isTelegram=True))
            else:
                # nonList 설정한 경우
                asyncio.create_task(find_Answer_From_AllCollected(
                    chatID, userID, message_str, token='*', isTelegram=True))
            return
        elif userID in dataInfo.premiumMember and '@' in message_edit and message_edit != '@':
            # 프리미엄 멤버이고, 기출문제 검색조건인 @ 이 있으면 검색 시작
            asyncio.create_task(find_Answer_From_AllCollected(
                chatID, userID, message_str, isTelegram=True))
            return
        else:
            # 입력한 문자에 맞는 문제 검색
            if len(message_edit) == 1:
                msg = "검색어를 2글자 이상 입력하세요. 😨"
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
                return
            asyncio.create_task(find_Question_From_UserSearch(
                chatID, userID, message_edit, num_items, isURL, isTelegram=True))
            return
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, telegram=False))

    return


async def console_input():
    '''
    콘솔로 답을 조회하는 함수
    '''
    global dataInfo, userInfo, telegramInfo

    userID = 'console'
    if userID not in dataInfo.userInfo:
        async with dataInfo.userInfo_lock:
            dataInfo.userInfo[userID] = dict()
            await userInfo.save_pickle(dataInfo.userInfo)

    while True:
        try:
            message_str = await aioconsole.ainput("무엇을 조회할까요? = ")
            message_edit = message_str.lower()

            # CommandHandler 구현
            if message_str.startswith("/"):
                message_str = message_str[1:].lower()
                if message_str == "status" or message_str == "s":
                    await get_user_status(None, None, isTelegram=False)
                    continue
                elif message_str == "nonlist":
                    await toggle_user_nonList(None, None, isTelegram=False)
                    continue
                elif message_str.startswith('answer'):
                    await set_answer_count(None, None, message_str=message_str, isTelegram=False)
                    continue
                else:
                    continue

            # answerInfo 데이터 업데이트
            if message_str.startswith(";;"):
                asyncio.create_task(run_admin_command(
                    None, userID, message_str, message_edit, None, isTelegram=False))
                continue

            # ;으로 시작하는 질문은 URL 링크만 리턴
            isURL = False
            if message_edit.startswith(";"):
                isURL = True
                message_edit = message_edit[1:]
                # 예약된 정답이 있으면 취소
                dataInfo.answerKey[f'{userID}_title'] = None

            if not bool(message_edit):
                # 입력값이 없으면 리턴
                continue

            logmsg = f'CONSOLE : {message_str}'
            print(logmsg)
            asyncio.create_task(writelog(logmsg, False))

            # 정답정보 업데이트
            if '*' not in message_edit:
                update_result = await update_answer_data(None, userID, message_str, message_edit, None, isTelegram=False)
                if update_result:
                    continue

            # message_edit가 콜론과 숫자로 구성되어 있는지 확인하고, 해당 숫자를 추출합니다.
            if ':' in message_edit:
                num_items, message_edit = await update_user_items_count(None, userID, message_edit, isTelegram=False)
            else:
                num_items = dataInfo.userInfo[userID].get(
                    'num_items', dataInfo.maxAnswerCnt)

            if not bool(message_edit):
                # 검색할 문제가 없으면 종료
                continue

            # 요청처리
            if is_integer(message_edit):
                # 문제후보 중 하나를 선택한 경우
                asyncio.create_task(get_Answer_For_Selected_Problem(
                    None, userID, message_edit, isTelegram=False))
                continue
            elif dataInfo.userInfo[userID].get('nextAllCollectedIndex', 0) != 0 and message_edit == "네":
                # 기출문제 검색 결과를 계속 출력한다고 한 경우
                asyncio.create_task(push_Next_AllCollected(
                    None, userID, isTelegram=False))
                continue
            elif dataInfo.userInfo[userID].get('nextPushIndex', 0) != 0 and message_edit == "네":
                # 문제 리스트를 계속 출력한다고 한 경우
                asyncio.create_task(push_Next_UserSearch(
                    None, userID, isTelegram=False))
                continue
            elif bool(dataInfo.userInfo[userID].get('title', False)) and '*' in message_edit and message_edit != '*':
                # 정답 찾기를 위한 제목이 있고, 검색조건인 * 이 있으면 검색 시작
                if not dataInfo.userInfo[userID].get('nonList', False) or len(dataInfo.userInfo[userID]['titleList']) == 1:
                    # 정답을 확인하고 싶은 문제를 선택하도록 설정한 경우
                    asyncio.create_task(find_Answer_From_CollectedData(
                        None, userID, message_str, isTelegram=False))
                else:
                    # nonList 설정한 경우
                    asyncio.create_task(find_Answer_From_AllCollected(
                        None, userID, message_str, token='*', isTelegram=False))
                continue
            elif userID in dataInfo.premiumMember and '@' in message_edit:
                # 정답 찾기를 위한 제목 상관없이 전체 수집 정보에서 검색 시작
                async with dataInfo.userInfo_lock:
                    # 정답 찾기를 할지 모르니 일단 저장
                    await userInfo.save_pickle(dataInfo.userInfo)
                asyncio.create_task(find_Answer_From_AllCollected(
                    None, userID, message_str, isTelegram=False))
                continue
            else:
                # 입력한 문자에 맞는 문제 검색
                if len(message_edit) == 1:
                    msg = "검색어를 2글자 이상 입력하세요. 😨"
                    print(msg)
                    continue
                asyncio.create_task(find_Question_From_UserSearch(
                    None, userID, message_edit, num_items, isURL, isTelegram=False))
                continue
        except Exception as e:
            msg = f'{traceback.format_exc()}'
            asyncio.create_task(writelog(msg, telegram=False))


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    상태조회 명령어 처리 함수
    '''
    global dataInfo, scriptInfo

    def get_help_file(filename):
        try:
            with open(fr'{scriptInfo.dir_path}\{filename}', "r", encoding="utf-8") as file:
                file_content = file.read()
                return file_content
        except FileNotFoundError:
            print(f"{filename} File not found.")
        except Exception as e:
            print(f"An error occurred while reading the {filename} file:", e)

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 멤버가 아니면 대화 거절
        if not check_member(userID):
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        file_content = get_help_file(dataInfo.helpFilename)
        # 도움말 알림
        msg = file_content.replace(
            '{maxAnswerCnt}', str(dataInfo.maxAnswerCnt))

        # 프리미엄 맴버 알림
        if userID in dataInfo.premiumMember:
            premium_file_content = get_help_file(dataInfo.premiumHelpFilename)
            msg += '\n\n' + \
                premium_file_content.replace(
                    '{maxAnswerLen}', str(dataInfo.maxAnswerLen))

        # 정답관리자 알림
        if userID in dataInfo.answerManageMember:
            answerManage_file_content = get_help_file(
                dataInfo.answerManageHelpFilename)
            replacements = {
                '{noti}': dataInfo.answerKey.get(f"{userID}_noti", False),
                '{alert}': dataInfo.answerKey.get(f"{userID}_alert", False),
                '{channel_noti}': not dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False)
            }
            msg += '\n\n' + \
                replace_content_with_user_settings(
                    answerManage_file_content, replacements)

        # 관리자 알림
        if userID in dataInfo.adminMember:
            admin_file_content = get_help_file(
                dataInfo.adminHelpFilename)

            # 리프레시 현황 확인
            refMsg = get_buf_refresh_status()

            # refresh_naver_buf 리프레시 현황 확인
            if not dataInfo.naverBuf_list:
                navMsg = "현재 refresh_naver_buf 가 실행중이지 않아요 😎"
            else:
                navMsg = f"⏳ {dict_values_to_string(dataInfo.naverBuf_list)}"

            replacements = {
                '{refresh}': refMsg,
                '{naverBuf_refresh}': navMsg
            }
            msg += '\n\n' + \
                replace_content_with_user_settings(
                    admin_file_content, replacements)

        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            userID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def get_user_status(update: Update, context: ContextTypes.DEFAULT_TYPE, isTelegram=True):
    '''
    상태조회 명령어 처리 함수
    '''
    global dataInfo

    try:
        if isTelegram:
            if not update.message:
                return

            chatID = str(update.message.chat_id)
            userID = str(update.message.from_user.id)
            username = update.message.from_user.full_name

            # 멤버가 아니면 대화 거절
            if not check_member(userID):
                asyncio.create_task(
                    send_reject_message(chatID, userID, username))
                return
        else:
            userID = 'console'

        # 설정값 확인
        msg = f'📌 정답알림 갯수 (/answer): {dataInfo.userInfo[userID].get("num_items", dataInfo.maxAnswerCnt)}' \
            f'\n📌 검색어 출력 (/nonlist) : {"문제와 답을 한번에" if dataInfo.userInfo[userID].get("nonList", False) else "선택한 문제의 답을"} 출력합니다.' \
            f'\n📌 이미지 출력(/image): 문제 이미지 크기를 {"작게" if dataInfo.userInfo[userID].get("image", True) else "크게"} 출력합니다.'
        if userID in dataInfo.premiumMember:
            msg += '\n📌 등급 : premium ✨'
        if userID in dataInfo.answerManageMember:
            msg += f'\n📌 알림모드 (/noti) : {dataInfo.answerKey.get(f"{userID}_noti", False)}' \
                f'\n📌 채널알림모드(/channel_noti): {not dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False)}'
        if userID in dataInfo.adminMember:
            msg += f'\n📌 Alert모드(/alert): {dataInfo.answerKey.get(f"{userID}_alert", False)}'

        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def toggle_user_nonList(update: Update, context: ContextTypes.DEFAULT_TYPE, isTelegram=True):
    '''
    검색결과를 문제를 먼저 선택살지 아니면 문제/압을 한번에 출력할지 설정을 toggle 하는 명령어
    '''
    global dataInfo, userInfo

    try:
        if isTelegram:
            if not update.message:
                return

            chatID = str(update.message.chat_id)
            userID = str(update.message.from_user.id)
            username = update.message.from_user.full_name

            # 멤버가 아니면 대화 거절
            if not check_member(userID):
                asyncio.create_task(
                    send_reject_message(chatID, userID, username))
                return
        else:
            userID = 'console'

        # nonList 설정
        async with dataInfo.userInfo_lock:
            dataInfo.userInfo[userID]['nonList'] = True if not dataInfo.userInfo[userID].get(
                'nonList', False) else False
            await userInfo.save_pickle(dataInfo.userInfo)

        # nonList 설정 알림
        msg = f'검색결과가 여러개인 경우 {"문제와 답을 한번에" if dataInfo.userInfo[userID].get("nonList", False) else "선택한 문제를"} 출력합니다. ✅'

        if isTelegram:
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            print(msg)

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def toggle_user_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    검색된 문제의 이미지 크기를 변경하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 멤버가 아니면 대화 거절
        if not check_member(userID):
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # image 설정
        async with dataInfo.userInfo_lock:
            dataInfo.userInfo[userID]['image'] = False if dataInfo.userInfo[userID].get(
                'image', True) else True
            await userInfo.save_pickle(dataInfo.userInfo)

        # image 설정알림
        msg = f'문제 이미지 크기를 {"작게" if dataInfo.userInfo[userID].get("image", True) else "크게"} 출력합니다. ✅'
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def toggle_noti_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    정답을 채널에 알리는 모드를 toogle 하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 정답관라자가 아니면 대화 거절
        if userID not in dataInfo.answerManageMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 정답알림 설정
        async with dataInfo.answerKey_lock:
            dataInfo.answerKey[f"{userID}_noti"] = False if dataInfo.answerKey.get(
                f"{userID}_noti", False) else True
            await answerKeyInfo.save_pickle(dataInfo.answerKey)

        # 설정알림
        msg = f'정답공유방에 정답을 {"알림" if dataInfo.answerKey.get(f"{userID}_noti", True) else "알리지 않습"}니다. ✅'
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(chatID, msg))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def toggle_channel_noti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    정답을 채널에 알릴때 텔레그램 알람을 toogle 하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 정답관라자가 아니면 대화 거절
        if userID not in dataInfo.answerManageMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 정답채널 알림 설정
        async with dataInfo.answerKey_lock:
            dataInfo.answerKey[f"{userID}_channel_noti_disable"] = False if dataInfo.answerKey.get(
                f"{userID}_channel_noti_disable", False) else True
            await answerKeyInfo.save_pickle(dataInfo.answerKey)

        # 정답채널 알림 설정 알림
        msg = f'정답 알림을 {"설정" if not dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False) else "해제"} 합니다. ✅'
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(chatID, msg))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def toggle_alert_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    사용자 봇 사용내역 알림 모드를 toggle 하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 정답알림 설정
        async with dataInfo.answerKey_lock:
            dataInfo.answerKey[f"{userID}_alert"] = False if dataInfo.answerKey.get(
                f"{userID}_alert", False) else True
            await answerKeyInfo.save_pickle(dataInfo.answerKey)

        # image 설정알림
        msg = f'Alert 모드를 {"설정" if dataInfo.answerKey.get(f"{userID}_alert", True) else "해제"} 합니다. ✅'
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(chatID, msg))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def set_answer_count(update: Update, context: ContextTypes.DEFAULT_TYPE, message_str=None, isTelegram=True):
    '''
    정답을 확인할 갯수를 설정하는 함수
    '''
    global dataInfo

    try:

        if isTelegram:
            if not update.message:
                return

            chatID = str(update.message.chat_id)
            userID = str(update.message.from_user.id)
            username = update.message.from_user.full_name

            # 멤버가 아니면 대화 거절
            if not check_member(userID):
                asyncio.create_task(
                    send_reject_message(chatID, userID, username))
                return

            args = context.args
            if not args:
                await update.message.reply_text("😅 정답을 확인할 갯수를 입력하세요. 예: /answer 10")
                return
        else:
            userID = 'console'

        try:
            # 정답수 설정
            if isTelegram:
                num_items = int(args[0])
            else:
                num_items = extract_number_after_command(
                    message_str, ['answer'])

            async with dataInfo.userInfo_lock:
                if num_items > dataInfo.maxAnswerBuf:
                    dataInfo.userInfo[userID]['num_items'] = dataInfo.maxAnswerBuf
                elif num_items > 0:
                    dataInfo.userInfo[userID]['num_items'] = num_items
                else:
                    dataInfo.userInfo[userID]['num_items'] = dataInfo.maxAnswerBuf
                await userInfo.save_pickle(dataInfo.userInfo)

            # 정답수 설정 알림
            msg = f'정답 알림 갯수를 {dataInfo.userInfo[userID]["num_items"]} 개로 설정합니다. 😎'
            if isTelegram:
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
            else:
                print(msg)

        except Exception as e:
            if isTelegram:
                await update.message.reply_text("😨 정답을 확인할 갯수를 다시 입력하세요. 예: /answer 10")
            else:
                print("😨 정답을 확인할 갯수를 다시 입력하세요. 예: /answer 10")
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def get_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    cashtree bot 사용자 현황을 조회하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 사용자 정보 확인
        userList = []
        for idx, userID in enumerate(dataInfo.userInfo):
            msg = f'{idx+1}. {dataInfo.userInfo[userID].get("username", userID)} ({userID})\n' \
                f'📌 정답알림 갯수 : {dataInfo.userInfo[userID].get("num_items", dataInfo.maxAnswerCnt)}\n' \
                f'📌 검색어 출력 : {"문제와 답을 한번에" if dataInfo.userInfo[userID].get("nonList", False) else "선택한 문제의 답을"} 출력합니다.\n' \
                f'📌 이미지 출력: 문제 이미지 크기를 {"작게" if dataInfo.userInfo[userID].get("image", True) else "크게"} 출력합니다.'
            if userID in dataInfo.premiumMember:
                msg += '\n📌 등급 : premium ✨'
            msg += '\n'
            userList.append(msg)

        msg = f'🎫 사용자 현황 📑\n' + '\n'.join(userList)

        # 사용자 정보 알림
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def get_admin_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    관리자 및 시스템 상태를 조회하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 리프레시 현황 확인
        refMsg = get_buf_refresh_status()

        # refresh_naver_buf 리프레시 현황 확인
        if not dataInfo.naverBuf_list:
            navMsg = "현재 refresh_naver_buf 가 실행중이지 않아요 😎"
        else:
            navMsg = f"⏳ {dict_values_to_string(dataInfo.naverBuf_list)}"

        # 설정값 확인
        msg = f'📌 알림모드 : {dataInfo.answerKey.get(f"{userID}_noti", False)}\n' \
            f'📌 Alert모드 : {dataInfo.answerKey.get(f"{userID}_alert", False)}\n' \
            f'📌 채널알림모드 : {not dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False)}\n' \
            f'📌 알림갯수 : {dataInfo.userInfo[userID].get("num_items", "전체")}\n' \
            f'📌 검색어 출력 : {"문제와 답을 한번에" if dataInfo.userInfo[userID].get("nonList", False) else "선택한 문제의 답을"} 출력합니다.\n' \
            f'📌 이미지 출력 : 문제 이미지 크기를 {"작게" if dataInfo.userInfo[userID].get("image", True) else "크게"} 출력합니다.\n' \
            f'📌 정답문제 : {dataInfo.answerKey.get(f"{userID}_title", "없음")}\n' \
            f'📌 정답후보 : {dataInfo.answerKey.get(f"{userID}_title_buf", "없음")}\n' \
            f'📌 취소문제 : {dataInfo.answerKey.get(f"{userID}_title_cancel", "없음")}\n' \
            f'📌 취소정답 : {dataInfo.answerKey.get(f"{userID}_answer_cancel", "없음")}\n' \
            f'📌 취소IDS : {dataInfo.answerKey.get(f"{userID}_cancel_ids", "없음")}\n' \
            f'📌 버퍼입력키 : {dataInfo.answerKey.get(f"{userID}_naver_key", "없음")}\n' \
            f'📌 버퍼취소키 : {dataInfo.answerKey.get(f"{userID}_naver_cancel_key", "없음")}\n' \
            f'📌 버퍼취소값 : {dataInfo.answerKey.get(f"{userID}_naver_cancel", "없음")}\n' \
            f'📌 naverBuf : {len(dataInfo.naverBuf)}\n' \
            f'📌 refresh_buf : {refMsg}\n' \
            f'📌 refresh_naver_buf : {navMsg}'

        # 관리자 및 시스템 상태 알림
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def get_naverBuf_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    naverBuf 수집현황을 조회하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # naverBuf 통계
        key_count = print_list_counts(dataInfo.naverBuf)
        msgList = [key_count[i:i + 100]
                   for i in range(0, len(key_count), 100)]

        # naverBuf 상태 알림
        asyncio.gather(*(asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, "\n".join(msg), disable_notification=True)) for msg in msgList))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def run_update_answerInfo_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    answerInfo 를 파일에서 다시 가져오는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # answerInfo 업데이트
        changes, deletions = await update_answerInfo()
        if bool(changes) or bool(deletions):
            messages = []
            if changes:  # changes에 항목이 있으면
                messages.append(f'추가된 정보: {changes}')
            if deletions:  # deletions에 항목이 있으면
                messages.append(f'삭제된 정보: {deletions}')
            msg = '\n'.join(messages)
        else:
            msg = f'{dataInfo.answerFilename} 파일에 업데이트된 내용이 없습니다. ✅'

        async with dataInfo.answerKey_lock:
            dataInfo.answerKey[f'{userID}_title'] = None
            await answerKeyInfo.save_pickle(dataInfo.answerKey)

        # 업데이트 상태 알림
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def run_check_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    정답 정보의 링크를 확인하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 링크 확인
        non_url_keys = find_keys_with_non_url_first_item(
            dataInfo.answerInfo)
        if not bool(non_url_keys):
            msg = f'모두 정상입니다! 👍'
        else:
            msg = f'URL이 없는 key : {non_url_keys}'

        # 링크 점검 결과 알림
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def get_refresh_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    문제의 정보를 refresh 하고 있는 상태를 확인하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 리프레시 현황 확인
        msg = get_buf_refresh_status()

        # 리프레시 현황 알림
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def get_naver_refresh_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    naverBuf 정보를 refresh 하고 있는 상태를 확인하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 리프레시 현황 확인
        if not dataInfo.naverBuf_list:
            msg = "현재 refresh_naver_buf 가 실행중이지 않아요 😎"
        else:
            msg = f"⏳ refresh_naver_buf : {dict_values_to_string(dataInfo.naverBuf_list)}"

        # 리프레시 현황 알림
        asyncio.create_task(telegramInfo.botInfo.bot.send_message(
            chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def run_refresh_naverBuf(update: Update, context: ContextTypes.DEFAULT_TYPE, message_str=None, isTelegram=True):
    '''
    naverBuf refresh 명령어 처리 함수
    '''
    global dataInfo

    try:

        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        args = context.args
        if not args:
            await update.message.reply_text("😅 refresh 할 naverBuf 갯수를 입력하세요. 예: /refresh_naverBuf 10")
            return

        try:
            # 정답수 설정
            try:
                maxRefresh = int(args[0])
                if not maxRefresh:
                    maxRefresh = dataInfo.maxRefresh
            except ValueError as e:
                err_msg = f"Error extract_number_after_command '{message_str}': {e} 🙄"
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, err_msg, disable_notification=True))
                return

            msg = f'naverBuf 를 {maxRefresh} 개 리프래쉬 합니다. ♻'
            # refresh 시작 알림
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))

            # naverBuf refresh
            asyncio.create_task(refresh_naver_buf(
                'refresh_naver_buf', maxRefresh, isTelegram))

        except Exception as e:
            if isTelegram:
                await update.message.reply_text("😨 refresh 할 naverBuf 갯수를 다시 입력하세요. 예: /refresh_naverBuf 10")
            else:
                print("😨 refresh 할 naverBuf 갯수를 다시 입력하세요. 예: /refresh_naverBuf 10")
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def run_refresh_buf(update: Update, context: ContextTypes.DEFAULT_TYPE, message_str=None, isTelegram=True):
    '''
    정답 정보를 update 하는 함수
    '''
    global dataInfo

    try:

        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        args = context.args
        if not args:
            await update.message.reply_text("😅 refresh 할 page 수를 입력하세요. 예: /refresh_buf 10")
            return

        try:
            # 정답수 설정
            try:
                PageCnt = int(args[0])
                if not PageCnt:
                    PageCnt = dataInfo.maxBackupPageCnt
                inverval = dataInfo.backupInterval if PageCnt > dataInfo.maxPageCnt else dataInfo.naverInterval
            except ValueError as e:
                err_msg = f"Error extract_number_after_command '{message_str}': {e} 🙄"
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, err_msg, disable_notification=True))
                return

            # buf 리프래쉬
            if not bool(dataInfo.answerKey.get(f"{userID}_title_buf", False)):
                msg = f'리프래쉬 할 문제를 먼저 검색하세요. 🙄'
                asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                    chatID, msg, disable_notification=True))
                return
            key = dataInfo.answerKey[f'{userID}_title_buf']
            asyncio.create_task(refresh_buf(
                key, PageCnt, inverval, True, chatID))

        except Exception as e:
            if isTelegram:
                await update.message.reply_text("😨 refresh 할 page 수를 다시 입력하세요. 예: /answer 10")
            else:
                print("😨 refresh 할 page 수를 다시 입력하세요. 예: /answer 10")
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def get_buf_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    문제의 buf 갯수를 확인하는 함수
    '''
    global dataInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관라자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        # 수집한 buf 갯수 조회
        if not bool(dataInfo.answerKey[f'{userID}_title_buf']):
            msg = f'naverBuf 에 정보가 있는지 확인할 문제를 선택하세요. 🙄'
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
            return
        key = dataInfo.answerKey[f'{userID}_title_buf']
        if key not in dataInfo.answerInfo:
            msg = f'{key} 라는 문제가 없습니다. 정보가 있는지 확인할 문제를 다시 선택하세요. 🤔'
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        elif 'smartstore.naver.com' in dataInfo.answerInfo[key][0] or 'brand.naver.com' in dataInfo.answerInfo[key][0]:
            # 스마트스토어 정답찾기
            store_url = dataInfo.answerInfo[key][0]
            # 버퍼 갯수 확인
            if store_url in dataInfo.naverBuf:
                msg = f"{key} : {len(dataInfo.naverBuf[store_url])} 개"
            else:
                msg = f"{key} : 검색정보 없음! 🤔"
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        elif 'place.naver.com' in dataInfo.answerInfo[key][0]:
            place_url = dataInfo.answerInfo[key][0]
            # 버퍼 갯수 확인
            if place_url in dataInfo.naverBuf:
                msg = f"{key} : {len(dataInfo.naverBuf[place_url])} 개"
            else:
                msg = f"{key} : 검색정보 없음! 🤔"
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        elif 'place.map.kakao.com' in dataInfo.answerInfo[key][0]:
            place_url = dataInfo.answerInfo[key][0]
            # 버퍼 갯수 확인
            if place_url in dataInfo.naverBuf:
                msg = f"{key} : {len(dataInfo.naverBuf[place_url])} 개"
            else:
                msg = f"{key} : 검색정보 없음! 🤔"
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))
        else:
            msg = f'{key} 는 올바른 URL이 아닙니다. 관리자에게 문의하세요. 😣'
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    메시지 핸들러
    '''
    global dataInfo, telegramInfo

    if update.message:
        chat_id = str(update.message.chat_id)
    elif update.edited_message:
        chat_id = str(update.edited_message.chat_id)
    elif update.channel_post:
        chat_id = str(update.channel_post.chat.id)
    elif update.edited_channel_post:
        chat_id = str(update.edited_channel_post.chat.id)

    if not chat_id:
        return
    elif chat_id.startswith('-'):
        asyncio.create_task(handle_channel_message(update, context))
    else:
        asyncio.create_task(handle_title_message(update, context))


async def refresh_naver_buf(kind, maxRefresh, isTelegram=True):
    '''
    naverBuf 내용을 갱신하는 함수
    maxRefresh : 갱신할 갯수
    '''
    global dataInfo, telegramInfo

    def update_remain_info():
        nonlocal progress_bar, task_id

        # 현재 진행률과 남은 시간 정보 가져오기
        progress = progress_bar.n / progress_bar.total
        remaining_seconds = progress_bar._time() - progress_bar.start_t
        if progress_bar.n == 0:
            remaining_time = "알 수 없음"
        else:
            remaining_seconds = remaining_seconds * \
                (progress_bar.total - progress_bar.n) / progress_bar.n
            remaining_time = format_time(remaining_seconds)
        # dataInfo.naverBufProgress = f"진행률: {progress:.2%}, 남은 시간: {remaining_time}"
        dataInfo.naverBuf_list[task_id] = f"진행률: {progress:.2%}, 남은 시간: {remaining_time}"

    # buf 가 비어있으면 종료
    if not dataInfo.naverBuf:
        return
    try:
        isOK = True
        failCnt = 0
        task_id = str(uuid.uuid4())
        keys_to_delete = []  # 삭제할 키들을 저장할 리스트
        start_index = dataInfo.naverBuf.get('refresh_offset', 0)
        keys = list(dataInfo.naverBuf.keys())
        if 'refresh_offset' in dataInfo.naverBuf:
            keys.remove('refresh_offset')  # refresh_offset 키는 제외
        total_keys = len(keys)
        end_index = start_index + maxRefresh

        # 필요한 수만큼의 키를 순환적으로 선택
        if end_index > total_keys:
            end_index = end_index - total_keys
            current_keys = keys[start_index:] + keys[:end_index]
        else:
            current_keys = keys[start_index:end_index]

        l = len(current_keys)
        with tqdm(total=l, desc=kind, leave=False, dynamic_ncols=True) as progress_bar:
            start_title = find_key_by_url(current_keys[0])
            end_title = find_key_by_url(current_keys[-1])
            msg = f'{start_title} 부터 {end_title} 까지 {l} 개 정보를 갱신합니다.'
            asyncio.create_task(writelog(msg, isTelegram))
            # dataInfo.naverBufProgress = f"진행률: 0%, 남은 시간: 알 수 없음"
            dataInfo.naverBuf_list[task_id] = f"진행률: 0%, 남은 시간: 알 수 없음"

            # 딕셔너리 키들을 리스트로 복사하여 순회
            for i, key in enumerate(current_keys):
                title = find_key_by_url(key)
                # 문제를 삭제한 경우 수집된 자료 삭제
                if not title:
                    keys_to_delete.append(key)  # 삭제할 키 추가
                    progress_bar.update(1)
                    # 현재 진행률과 남은 시간 정보 가져오기
                    update_remain_info()
                    continue

                # 이미 리프레시 대기열에 있는지 확인
                if key in dataInfo.refresh_list:
                    progress_bar.update(1)
                    # 현재 진행률과 남은 시간 정보 가져오기
                    update_remain_info()
                    continue

                # 리프레시 대기열에 추가
                async with dataInfo.refresh_list_lock:
                    dataInfo.refresh_list[key] = dict()
                    dataInfo.refresh_list[key]['title'] = title
                    dataInfo.refresh_list[key]['PageCnt'] = dataInfo.maxRefreshPageCnt

                # 데이터 재수집
                while True:
                    async with dataInfo.refresh_buf_lock:
                        if len(dataInfo.refresh_buf) < dataInfo.maxWorkers:
                            break
                    # Wait for 1 second before checking again
                    await asyncio.sleep(1)

                if 'place.naver.com' in key:
                    # place 정보 확인
                    backup_result, _ = await get_place_answer(key, dataInfo.maxRefreshPageCnt, dataInfo.refreshInterval, None)
                elif ('smartstore.naver.com' in key or 'brand.naver.com' in key):
                    # 스마트스토어 정답찾기
                    backup_result, _ = await get_store_answer(key, dataInfo.maxRefreshPageCnt, dataInfo.refreshInterval, None)
                if 'place.map.kakao.com' in key:
                    # kakao place 정보 확인
                    backup_result, _ = await get_kakao_place_answer(key, dataInfo.maxRefreshPageCnt, dataInfo.refreshInterval, None)
                else:
                    # place 나 smartstore 가 아닌 경우 pass
                    backup_result = True

                # 리프레시 대기열에서 제거
                async with dataInfo.refresh_list_lock:
                    del dataInfo.refresh_list[key]

                if not backup_result:
                    isOK = False
                    failCnt = failCnt + 1

                # 순환 로직 관리
                new_offset = (start_index + i + 1) % total_keys
                async with dataInfo.naverBuf_lock:
                    dataInfo.naverBuf['refresh_offset'] = new_offset

                progress_bar.update(1)
                # 현재 진행률과 남은 시간 정보 가져오기
                update_remain_info()

                # 다음 질문 갱신시간까지 interval
                await asyncio.sleep(dataInfo.naverInterval*30)

        msg = f'{start_title} 부터 {end_title} 까지 정보갱신을 완료했습니다.'
        asyncio.create_task(writelog(msg, isTelegram))
        # dataInfo.naverBufProgress = None
        del dataInfo.naverBuf_list[task_id]

        # 순회가 끝난 후 삭제할 키들을 처리
        async with dataInfo.naverBuf_lock:
            for key in keys_to_delete:
                del dataInfo.naverBuf[key]
                msg = f'{key} 사이트 수집정보를 삭제했습니다.'
                asyncio.create_task(writelog(msg, isTelegram))
            await naverBufInfo.save_pickle(dataInfo.naverBuf)

            # 순환 로직 관리
            new_offset = (start_index + i + 1) % total_keys
            dataInfo.naverBuf['refresh_offset'] = new_offset

        # 백업실패가 있으면 알림
        if not isOK:
            msg = f"[refresh_naver_buf] {failCnt} 개 사이트 정보수집에 실패했습니다. 로그를 확인하세요."
            for adminUser in dataInfo.adminMember:
                asyncio.create_task(
                    telegramInfo.botInfo.bot.send_message(adminUser, msg))

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def enable_alert_mode(kind):
    '''
    alert 모드를 enable 하고,
    noti 모드를 enable 하는 함수
    '''
    global dataInfo, telegramInfo

    try:
        print(f'{kind} 실행!')
        # alert 모드 설정
        for userID in dataInfo.adminMember:
            if not dataInfo.answerKey.get(f'{userID}_alert', False):
                # alert 모드 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_alert'] = True
                msg = f'alert 모드가 {"ON" if dataInfo.answerKey[f"{userID}_alert"] else "OFF"} 되었습니다. 👀'
                if userID != 'console':
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(userID, msg))
                else:
                    print(msg)

        # noti 모드 설정
        for userID in dataInfo.answerManageMember:
            if not dataInfo.answerKey.get(f"{userID}_noti", False):
                # noti 모드 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_noti'] = True
                msg = f'정답 알림모드가 {"ON" if dataInfo.answerKey[f"{userID}_noti"] else "OFF"} 되었습니다. 👀'
                if userID != 'console':
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(userID, msg,))
                else:
                    print(msg)

        # 설정 저장
        async with dataInfo.answerKey_lock:
            await answerKeyInfo.save_pickle(dataInfo.answerKey)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def disable_alert_mode(kind):
    '''
    alert 모드를 disable 하고,
    noti 모드를 enable 하는 함수
    '''
    global dataInfo, telegramInfo

    try:
        print(f'{kind} 실행!')
        # alert 모드 설정
        for userID in dataInfo.adminMember:
            if dataInfo.answerKey.get(f'{userID}_alert', False):
                # alert 모드 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_alert'] = False
                msg = f'alert 모드가 {"ON" if dataInfo.answerKey[f"{userID}_alert"] else "OFF"} 되었습니다. 👀'
                if userID != 'console':
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(userID, msg))
                else:
                    print(msg)

        # noti 모드 설정
        for userID in dataInfo.answerManageMember:
            if not dataInfo.answerKey.get(f"{userID}_noti", False):
                # noti 모드 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_noti'] = True
                msg = f'정답 알림모드가 {"ON" if dataInfo.answerKey[f"{userID}_noti"] else "OFF"} 되었습니다. 👀'
                if userID != 'console':
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(userID, msg))
                else:
                    print(msg)

        # 설정 저장
        async with dataInfo.answerKey_lock:
            await answerKeyInfo.save_pickle(dataInfo.answerKey)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
    asyncio.create_task(writelog(msg, False))
    return


async def enable_noti_mode(kind):
    '''
    정답 알림 모드를 enable 하는 함수
    '''
    global dataInfo, telegramInfo

    try:
        print(f'{kind} 실행!')
        # noti 모드 설정
        for userID in dataInfo.answerManageMember:
            if not dataInfo.answerKey.get(f"{userID}_noti", False):
                # noti 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f"{userID}_noti"] = True
                # 설정알림
                msg = f'정답공유방에 정답을 {"알림" if dataInfo.answerKey.get(f"{userID}_noti", True) else "알리지 않습"}니다. ✅'
                if userID != 'console':
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(userID, msg))
                else:
                    print(msg)

        # 설정 저장
        async with dataInfo.answerKey_lock:
            await answerKeyInfo.save_pickle(dataInfo.answerKey)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def disable_noti_mode(kind):
    '''
    정답 알림 모드를 disable 하는 함수
    '''
    global dataInfo, telegramInfo

    try:
        print(f'{kind} 실행!')
        # noti 모드 설정
        for userID in dataInfo.answerManageMember:
            if dataInfo.answerKey.get(f"{userID}_noti", False):
                # noti 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f"{userID}_noti"] = False
                # 설정알림
                msg = f'정답공유방에 정답을 {"알림" if dataInfo.answerKey.get(f"{userID}_noti", True) else "알리지 않습"}니다. ✅'
                if userID != 'console':
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(userID, msg))
                else:
                    print(msg)

        # 설정 저장
        async with dataInfo.answerKey_lock:
            await answerKeyInfo.save_pickle(dataInfo.answerKey)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def enable_channel_noti_mode(kind):
    '''
    채널방 정답 전송시 알림 모드를 enable 하는 함수
    '''
    global dataInfo, telegramInfo

    try:
        print(f'{kind} 실행!')
        # channel_noti 모드 설정
        for userID in dataInfo.answerManageMember:
            if dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False):
                # channel_noti 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_channel_noti_disable'] = False
                msg = f'채널 알림 모드가 {"ON" if not dataInfo.answerKey[f"{userID}_channel_noti_disable"] else "OFF"} 되었습니다. 👀'
                if userID != 'console':
                    asyncio.create_task(
                        telegramInfo.botInfo.bot.send_message(userID, msg))
                else:
                    print(msg)

        # 설정 저장
        async with dataInfo.answerKey_lock:
            await answerKeyInfo.save_pickle(dataInfo.answerKey)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def disable_channel_noti_mode(kind):
    '''
    채널방 정답 전송시 알림 모드를 disable 하는 함수
    '''
    global dataInfo, telegramInfo

    try:
        print(f'{kind} 실행!')
        # channel_noti 모드 설정
        for userID in dataInfo.answerManageMember:
            if not dataInfo.answerKey.get(f"{userID}_channel_noti_disable", False):
                # channel_noti 모드 설정
                async with dataInfo.answerKey_lock:
                    dataInfo.answerKey[f'{userID}_channel_noti_disable'] = True
                msg = f'채널 알림 모드가 {"ON" if not dataInfo.answerKey[f"{userID}_channel_noti_disable"] else "OFF"} 되었습니다. 👀'
                if userID != 'console':
                    asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                        userID, msg, disable_notification=True))
                else:
                    print(msg)

        # 설정 저장
        async with dataInfo.answerKey_lock:
            await answerKeyInfo.save_pickle(dataInfo.answerKey)
    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def update_user_agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    user agent를 업데이트하는 명령어 처리 함수
    '''
    global dataInfo, configInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관리자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        args = context.args
        if not args:
            await update.message.reply_text("😅 새로운 user agent을 입력하세요. 예: /agent NEW_USER_AGENT")
            return

        try:
            # 새로운 토큰 값 가져오기
            new_agent = ' '.join(args)

            # 토큰 길이 검증 (최소한의 검증)
            if len(new_agent) < 1:
                await update.message.reply_text("😨 올바르지 않은 user agent 형식입니다. user agent 값을 다시 확인해주세요.")
                return

            # 이전 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            old_agent_display = dataInfo.User_Agent[-10:] + \
                "..." if dataInfo.User_Agent else "None"

            # dataInfo.User_Agent 업데이트
            dataInfo.User_Agent = new_agent

            # ini 파일 업데이트
            configInfo.config['DATA']['user_agent'] = f"'{new_agent}'"
            await configInfo.change_config_file()

            # 새 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            new_agent_display = new_agent[-10:] + "..."

            # 성공 메시지 전송
            msg = f'✅ User Agent 가 성공적으로 업데이트되었습니다.\n' \
                f'이전: {old_agent_display}\n' \
                f'변경: {new_agent_display}'

            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))

            # 로그 기록
            log_msg = f'User Agent updated by {username}({userID}): {old_agent_display} → {new_agent_display}'
            asyncio.create_task(writelog(log_msg, telegram=True))

        except Exception as e:
            await update.message.reply_text("😨 user agent 업데이트 중 오류가 발생했습니다. 다시 시도해주세요.")
            error_msg = f'User Agent update error: {traceback.format_exc()}'
            asyncio.create_task(writelog(error_msg, telegram=False))
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def update_store_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    store_token을 업데이트하는 명령어 처리 함수
    '''
    global dataInfo, configInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관리자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        args = context.args
        if not args:
            await update.message.reply_text("😅 새로운 store token을 입력하세요. 예: /token YOUR_NEW_TOKEN")
            return

        try:
            # 새로운 토큰 값 가져오기
            new_token = args[0]

            # 토큰 길이 검증 (최소한의 검증)
            if len(new_token) < 50:
                await update.message.reply_text("😨 올바르지 않은 토큰 형식입니다. 토큰을 다시 확인해주세요.")
                return

            # 이전 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            old_token_display = dataInfo.store_token[:10] + \
                "..." if dataInfo.store_token else "None"

            # dataInfo.store_token 업데이트
            dataInfo.store_token = new_token

            # ini 파일 업데이트
            configInfo.config['DATA']['store_token'] = f"'{new_token}'"
            await configInfo.change_config_file()

            # 새 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            new_token_display = new_token[:10] + "..."

            # 성공 메시지 전송
            msg = f'✅ Store token이 성공적으로 업데이트되었습니다.\n' \
                f'이전: {old_token_display}\n' \
                f'변경: {new_token_display}'

            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))

            # 로그 기록
            log_msg = f'Store token updated by {username}({userID}): {old_token_display} → {new_token_display}'
            asyncio.create_task(writelog(log_msg, telegram=True))

        except Exception as e:
            await update.message.reply_text("😨 토큰 업데이트 중 오류가 발생했습니다. 다시 시도해주세요.")
            error_msg = f'Store token update error: {traceback.format_exc()}'
            asyncio.create_task(writelog(error_msg, telegram=False))
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def update_store_nnb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    store_nnb를 업데이트하는 명령어 처리 함수
    '''
    global dataInfo, configInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관리자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        args = context.args
        if not args:
            await update.message.reply_text("😅 새로운 store nnb을 입력하세요. 예: /nnb YOUR_NEW_NNB")
            return

        try:
            # 새로운 토큰 값 가져오기
            new_store_nnb = args[0]

            # 토큰 길이 검증 (최소한의 검증)
            if len(new_store_nnb) < 10:
                await update.message.reply_text("😨 올바르지 않은 토큰 형식입니다. 토큰을 다시 확인해주세요.")
                return

            # 이전 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            old_nnb_display = dataInfo.store_nnb[:10] + \
                "..." if dataInfo.store_nnb else "None"

            # dataInfo.store_nnb 업데이트
            dataInfo.store_nnb = new_store_nnb

            # ini 파일 업데이트
            configInfo.config['DATA']['store_nnb'] = f"'{new_store_nnb}'"
            await configInfo.change_config_file()

            # 새 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            new_store_nnb_display = new_store_nnb[:10] + "..."

            # 성공 메시지 전송
            msg = f'✅ Store NNB 가 성공적으로 업데이트되었습니다.\n' \
                f'이전: {old_nnb_display}\n' \
                f'변경: {new_store_nnb_display}'

            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))

            # 로그 기록
            log_msg = f'Store NNB updated by {username}({userID}): {old_nnb_display} → {new_store_nnb_display}'
            asyncio.create_task(writelog(log_msg, telegram=True))

        except Exception as e:
            await update.message.reply_text("😨 토큰 업데이트 중 오류가 발생했습니다. 다시 시도해주세요.")
            error_msg = f'Store NNB update error: {traceback.format_exc()}'
            asyncio.create_task(writelog(error_msg, telegram=False))
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def update_store_fwb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    store_fwb를 업데이트하는 명령어 처리 함수
    '''
    global dataInfo, configInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관리자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        args = context.args
        if not args:
            await update.message.reply_text("😅 새로운 store fwb을 입력하세요. 예: /fwb YOUR_NEW_NNB")
            return

        try:
            # 새로운 토큰 값 가져오기
            new_store_fwb = args[0]

            # 토큰 길이 검증 (최소한의 검증)
            if len(new_store_fwb) < 10:
                await update.message.reply_text("😨 올바르지 않은 토큰 형식입니다. 토큰을 다시 확인해주세요.")
                return

            # 이전 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            old_fwb_display = dataInfo.store_fwb[:10] + \
                "..." if dataInfo.store_fwb else "None"

            # dataInfo.store_fwb 업데이트
            dataInfo.store_fwb = new_store_fwb

            # ini 파일 업데이트
            configInfo.config['DATA']['store_fwb'] = f"'{new_store_fwb}'"
            await configInfo.change_config_file()

            # 새 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            new_store_fwb_display = new_store_fwb[:10] + "..."

            # 성공 메시지 전송
            msg = f'✅ Store NNB 가 성공적으로 업데이트되었습니다.\n' \
                f'이전: {old_fwb_display}\n' \
                f'변경: {new_store_fwb_display}'

            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))

            # 로그 기록
            log_msg = f'Store FWB updated by {username}({userID}): {old_fwb_display} → {new_store_fwb_display}'
            asyncio.create_task(writelog(log_msg, telegram=True))

        except Exception as e:
            await update.message.reply_text("😨 토큰 업데이트 중 오류가 발생했습니다. 다시 시도해주세요.")
            error_msg = f'Store FWB update error: {traceback.format_exc()}'
            asyncio.create_task(writelog(error_msg, telegram=False))
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return


async def update_store_buc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''
    store_buc를 업데이트하는 명령어 처리 함수
    '''
    global dataInfo, configInfo

    try:
        if not update.message:
            return

        chatID = str(update.message.chat_id)
        userID = str(update.message.from_user.id)
        username = update.message.from_user.full_name

        # 관리자가 아니면 대화 거절
        if userID not in dataInfo.adminMember:
            asyncio.create_task(send_reject_message(chatID, userID, username))
            return

        args = context.args
        if not args:
            await update.message.reply_text("😅 새로운 store buc을 입력하세요. 예: /buc YOUR_NEW_NNB")
            return

        try:
            # 새로운 토큰 값 가져오기
            new_store_buc = args[0]

            # 토큰 길이 검증 (최소한의 검증)
            if len(new_store_buc) < 10:
                await update.message.reply_text("😨 올바르지 않은 토큰 형식입니다. 토큰을 다시 확인해주세요.")
                return

            # 이전 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            old_buc_display = dataInfo.store_buc[:10] + \
                "..." if dataInfo.store_buc else "None"

            # dataInfo.store_buc 업데이트
            dataInfo.store_buc = new_store_buc

            # ini 파일 업데이트
            configInfo.config['DATA']['store_buc'] = f"'{new_store_buc}'"
            await configInfo.change_config_file()

            # 새 토큰 정보 (로그용, 보안을 위해 일부만 표시)
            new_store_buc_display = new_store_buc[:10] + "..."

            # 성공 메시지 전송
            msg = f'✅ Store NNB 가 성공적으로 업데이트되었습니다.\n' \
                f'이전: {old_buc_display}\n' \
                f'변경: {new_store_buc_display}'

            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chatID, msg, disable_notification=True))

            # 로그 기록
            log_msg = f'Store BUC updated by {username}({userID}): {old_buc_display} → {new_store_buc_display}'
            asyncio.create_task(writelog(log_msg, telegram=True))

        except Exception as e:
            await update.message.reply_text("😨 토큰 업데이트 중 오류가 발생했습니다. 다시 시도해주세요.")
            error_msg = f'Store BUC update error: {traceback.format_exc()}'
            asyncio.create_task(writelog(error_msg, telegram=False))
            return

    except Exception as e:
        msg = f'{traceback.format_exc()}'
        asyncio.create_task(writelog(msg, False))
    return

# 주어진 시간에 함수를 실행하는 비동기 함수


async def run_at_specific_time(target_func, args, hour, minute):
    '''
    지정된 시간에 비동기 함수를 실행하고, 그 후에는 다음 날 같은 시간까지 대기합니다.
    비동기 이벤트 루프를 사용하여, 지정된 시간까지 대기 후 함수를 실행합니다.
    '''
    while True:
        now = datetime.now()
        next_run_time = now.replace(
            hour=hour, minute=minute, second=0, microsecond=0)
        # 이미 지정 시간을 지났다면, 다음 날로 설정
        if next_run_time <= now:
            next_run_time += relativedelta(days=1)
        # 다음 실행까지 대기
        wait_time = (next_run_time - now).total_seconds()
        msg = f"{target_func.__name__}: Waiting for {wait_time} seconds until the next run at {next_run_time}."
        print(msg)
        asyncio.create_task(writelog(msg, False))  # 로그 기록은 비동기로 처리
        await asyncio.sleep(wait_time)

        msg = f"{target_func.__name__}: Executing the target function at {datetime.now()}."
        print(msg)
        asyncio.create_task(writelog(msg, False))
        try:
            await target_func(*args)  # 비동기 함수가 호출되도록 변경
        except Exception as e:
            error_msg = f"An error occurred while executing the target function: {str(e)}"
            print(error_msg)
            asyncio.create_task(writelog(error_msg, False))  # 에러 로그 기록

        await asyncio.sleep(60)  # 중복 실행 방지


# 텔레그램 봇 설정 및 실행
async def main():
    # CONFIG 확인
    await getConfig()

    # proxyInfo.use_socks()

    # 백업된 answerKey 가져오기
    dataInfo.answerKey = await answerKeyInfo.get_all_pickle()
    for userID in dataInfo.answerManageMember:
        dataInfo.answerKey[f'{userID}_title'] = None

    # 백업된 naver buf 가져오기
    dataInfo.naverBuf = await naverBufInfo.get_all_pickle()

    # 백업된 user info 가져오기
    dataInfo.userInfo = await userInfo.get_all_pickle()

    # naverBuf 갱신 스케줄 설정
    for time_str in dataInfo.buf_refresh_time:
        refresh_hour, refresh_min = map(int, time_str.split(':'))
        refreshCnt = dataInfo.buf_refresh_time[time_str]
        asyncio.create_task(run_at_specific_time(
            refresh_naver_buf, ('refresh_naver_buf', refreshCnt), refresh_hour, refresh_min))

    # alert 모드 스케줄 설정
    for time_str in dataInfo.enable_alertmode_time:
        refresh_hour, refresh_min = map(int, time_str.split(':'))
        asyncio.create_task(run_at_specific_time(
            enable_alert_mode, ('enable_alert_mode', ), refresh_hour, refresh_min))
    for time_str in dataInfo.disable_alertmode_time:
        refresh_hour, refresh_min = map(int, time_str.split(':'))
        asyncio.create_task(run_at_specific_time(
            disable_alert_mode, ('disable_alert_mode', ), refresh_hour, refresh_min))

    # noti 모드 스케줄 설정
    for time_str in dataInfo.enable_notimode_time:
        refresh_hour, refresh_min = map(int, time_str.split(':'))
        asyncio.create_task(run_at_specific_time(
            enable_noti_mode, ('enable_noti_mode', ), refresh_hour, refresh_min))
    for time_str in dataInfo.disable_notimode_time:
        refresh_hour, refresh_min = map(int, time_str.split(':'))
        asyncio.create_task(run_at_specific_time(
            disable_noti_mode, ('disable_noti_mode', ), refresh_hour, refresh_min))

    # channel_noti 모드 스케줄 설정
    for time_str in dataInfo.enable_channel_notimode_time:
        refresh_hour, refresh_min = map(int, time_str.split(':'))
        asyncio.create_task(run_at_specific_time(
            enable_channel_noti_mode, ('enable_channel_noti_mode', ), refresh_hour, refresh_min))
    for time_str in dataInfo.disable_channel_notimode_time:
        refresh_hour, refresh_min = map(int, time_str.split(':'))
        asyncio.create_task(run_at_specific_time(
            disable_channel_noti_mode, ('disable_channel_noti_mode', ), refresh_hour, refresh_min))

    # console_input 실행
    # await console_input()
    asyncio.create_task(console_input())

    # 봇 실행 재시도 루프
    while True:
        try:
            # ApplicationBuilder를 이용해 봇 애플리케이션을 생성
            telegramInfo.initialize_bot(proxyInfo.url)

            telegramInfo.botInfo.add_handler(CommandHandler(
                ["help", "h"], show_help))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["status", "s"], get_user_status))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["nonlist"], toggle_user_nonList))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["image"], toggle_user_image))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["noti"], toggle_noti_mode))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["channel_noti"], toggle_channel_noti))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["alert"], toggle_alert_mode))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["answer"], set_answer_count))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["userInfo"], get_user_info))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["adminInfo"], get_admin_info))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["naverBuf_info"], get_naverBuf_count))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["reload"], run_update_answerInfo_reload))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["link"], run_check_link))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["refresh"], get_refresh_info))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["naverBuf_refresh"], get_naver_refresh_info))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["refresh_naverBuf"], run_refresh_naverBuf))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["refresh_buf"], run_refresh_buf))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                ["count_buf"], get_buf_count))  # 명령어 핸들러 사용
            telegramInfo.botInfo.add_handler(CommandHandler(
                # user agent 업데이트 명령어 핸들러
                ["agent"], update_user_agent_command))
            telegramInfo.botInfo.add_handler(CommandHandler(
                # store token 업데이트 명령어 핸들러
                ["token"], update_store_token_command))
            telegramInfo.botInfo.add_handler(CommandHandler(
                # nnb 업데이트 명령어 핸들러
                ["nnb"], update_store_nnb_command))
            telegramInfo.botInfo.add_handler(CommandHandler(
                # fwb 업데이트 명령어 핸들러
                ["fwb"], update_store_fwb_command))
            telegramInfo.botInfo.add_handler(CommandHandler(
                # buc 업데이트 명령어 핸들러
                ["buc"], update_store_buc_command))
            telegramInfo.botInfo.add_handler(MessageHandler(
                # 메시지 핸들러 사용
                filters.TEXT & (~filters.COMMAND), message_handler))

            # 봇 실행 메시지 전송
            asyncio.create_task(telegramInfo.botInfo.bot.send_message(
                chat_id=telegramInfo.adminChatID, text=f"[{scriptInfo.script_name}] 봇을 실행합니다 🙌"))

            # 봇 실행
            while True:
                try:
                    await telegramInfo.botInfo.run_polling()  # 비동기 실행
                except NetworkError as e:
                    if "timed out" in str(e).lower():
                        error_msg = "Connection timed out. Retrying in 1 second..."
                        asyncio.create_task(writelog(error_msg, False))
                        print(error_msg)
                        await asyncio.sleep(1)  # 1 초 후
                    else:
                        error_msg = f"Connection error: {str(e)}. Retrying in 1 second..."
                        asyncio.create_task(writelog(error_msg, False))
                        print(error_msg)
                        await asyncio.sleep(1)  # 1 초 후
        except Exception as e:
            msg = f'{traceback.format_exc()}'
            asyncio.create_task(writelog(msg, False))
            await asyncio.sleep(1)  # 에러 발생 시 1초 후 재시도

if __name__ == '__main__':
    # 스크립트 정보
    configInfo = ConfigInfo()
    proxyInfo = ProxyInfo()
    telegramInfo = TelegramInfo()
    answerKeyInfo = ImportFileInfo()
    naverBufInfo = ImportFileInfo()
    userInfo = ImportFileInfo()
    dataInfo = DataInfo()

    nest_asyncio.apply()
    asyncio.run(main())