"""腾讯云 COS 客户端封装模块。

职责:
    - get_sts_credentials(): 调用腾讯云 STS GetFederationToken 生成临时密钥
      （使用 tencentcloud-sdk-python，策略限定到用户目录，最小权限）。
    - head_object(): HEAD Object 校验文件完整性（纯 HTTP + COS XML API 签名实现）。
    - delete_object(): 删除 COS 文件（纯 HTTP + 签名实现）。
    - generate_presigned_url(): 生成预签名访问 URL（签名放查询参数，无需请求头）。

说明: HEAD/DELETE/预签名未引入 cos-python-sdk-v5，直接按 COS XML API 签名规范
    （q-sign-algorithm=sha1）用 requests + hmac 实现，减少依赖。
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

import requests
from tencentcloud.common import credential
from tencentcloud.sts.v20180813 import models as sts_models
from tencentcloud.sts.v20180813 import sts_client

from app.core.config import settings

logger = logging.getLogger(__name__)

# STS 临时密钥授予的 COS 写操作（含分片上传全流程）
_STS_UPLOAD_ACTIONS = [
    "name/cos:PutObject",
    "name/cos:InitiateMultipartUpload",
    "name/cos:ListMultipartUploads",
    "name/cos:ListParts",
    "name/cos:UploadPart",
    "name/cos:CompleteMultipartUpload",
    "name/cos:AbortMultipartUpload",
]


class CosError(Exception):
    """COS 服务操作异常（路由层转502）。"""


class CosClient:
    """腾讯云 COS 客户端封装（STS临时密钥 + 管理端对象操作）。"""

    def get_sts_credentials(self, resource_prefix: str) -> dict:
        """调用 STS 生成限定目录的临时上传密钥。

        策略精确限定到 resource_prefix（如 resumes/123），用户仅能
        上传到自己目录下，无法越权写他人目录。

        Args:
            resource_prefix: 允许写入的 COS Key 前缀（不含通配符）。

        Returns:
            包含 tmp_secret_id / tmp_secret_key / session_token / expired_time 的字典。

        Raises:
            CosError: STS 调用失败（密钥未配置、网络异常、策略非法等）。
        """
        if not settings.COS_SECRET_ID or not settings.COS_SECRET_KEY:
            raise CosError("COS永久密钥未配置（COS_SECRET_ID/COS_SECRET_KEY）")

        # 资源六段式: qcs::cos:{region}:uid/{appid}:{bucket}/{prefix}/*
        appid = self.get_appid()
        resource = f"qcs::cos:{settings.COS_REGION}:uid/{appid}:{settings.COS_BUCKET}/{resource_prefix}/*"
        policy = {
            "version": "2.0",
            "statement": [
                {
                    "effect": "allow",
                    "action": _STS_UPLOAD_ACTIONS,
                    "resource": [resource],
                }
            ],
        }

        try:
            cred = credential.Credential(settings.COS_SECRET_ID, settings.COS_SECRET_KEY)
            # GetFederationToken要求地域参数：SDK通过客户端初始化的region走X-TC-Region公共头传递，
            # 不能在请求对象上动态设置Region属性（AbstractModel序列化会将其转为"Egion"导致UnknownParameter）
            client = sts_client.StsClient(cred, settings.COS_REGION)
            req = sts_models.GetFederationTokenRequest()
            req.Name = "interview-tool-upload"
            req.Policy = json.dumps(policy)
            req.DurationSeconds = settings.COS_STS_DURATION
            resp = client.GetFederationToken(req)
        except Exception:
            logger.exception("调用STS获取临时密钥失败: resource=%s", resource)
            raise CosError("获取STS临时密钥失败")

        return {
            "tmp_secret_id": resp.Credentials.TmpSecretId,
            "tmp_secret_key": resp.Credentials.TmpSecretKey,
            "session_token": resp.Credentials.Token,
            "expired_time": resp.ExpiredTime,
        }

    def head_object(self, cos_key: str) -> dict | None:
        """HEAD Object 获取对象元数据，用于回调时校验文件完整性。

        Args:
            cos_key: COS 对象 Key。

        Returns:
            包含 content_length / content_type / etag 的字典；对象不存在返回None。

        Raises:
            CosError: COS 服务异常（非404的网络/服务端错误）。
        """
        url = self._build_object_url(cos_key)
        response = self._signed_request("HEAD", url)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.error("HEAD Object失败: key=%s status=%s", cos_key, response.status_code)
            raise CosError(f"HEAD Object失败: HTTP {response.status_code}")
        etag = response.headers.get("ETag", "").strip('"')
        return {
            "content_length": int(response.headers.get("Content-Length", "0")),
            "content_type": response.headers.get("Content-Type", ""),
            "etag": etag,
        }

    def delete_object(self, cos_key: str) -> bool:
        """删除 COS 对象。

        Args:
            cos_key: COS 对象 Key。

        Returns:
            是否成功删除（对象不存在视为成功，幂等）。

        Raises:
            CosError: COS 服务异常。
        """
        url = self._build_object_url(cos_key)
        response = self._signed_request("DELETE", url)
        # 204删除成功；404视为幂等成功；403无权限或其他状态码报错
        if response.status_code in (204, 404):
            return True
        logger.error("DELETE Object失败: key=%s status=%s", cos_key, response.status_code)
        raise CosError(f"DELETE Object失败: HTTP {response.status_code}")

    def get_object_bytes(self, cos_key: str) -> bytes | None:
        """GET Object 下载对象内容（回调内计算文件SHA256去重用）。

        Args:
            cos_key: COS 对象 Key。

        Returns:
            文件内容字节；对象不存在返回None。

        Raises:
            CosError: COS 服务异常。
        """
        url = self._build_object_url(cos_key)
        response = self._signed_request("GET", url, timeout=30)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.error("GET Object失败: key=%s status=%s", cos_key, response.status_code)
            raise CosError(f"GET Object失败: HTTP {response.status_code}")
        return response.content

    def put_object(self, cos_key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """PUT Object 上传对象（管理端永久密钥签名）。

        按 COS 官方签名规范，HttpString 固定为
        "HttpMethod\\nUriPathname\\nHttpParameters\\nHttpHeaders\\n"，不带 Body 摘要行；
        Body 完整性通过可选的 x-cos-content-sha1 请求头传递并纳入签名（参考官方示例）。
        供测试与未来服务端上传场景复用。

        Args:
            cos_key: COS 对象 Key。
            content: 对象内容字节。
            content_type: MIME 类型。

        Returns:
            COS 返回的 ETag（单块上传即对象 MD5）。

        Raises:
            CosError: 上传失败（HTTP 非 200）。
        """
        url = self._build_object_url(cos_key)
        now = int(time.time())
        key_time = f"{now};{now + 600}"
        content_sha1 = hashlib.sha1(content).hexdigest()
        # 仅签 x-cos-content-sha1 一个头（值 urlencode），HeaderList 与之对应
        http_headers = f"x-cos-content-sha1={quote(content_sha1, safe='')}"
        signature = self._calc_signature("put", self._path_from_url(url), "", http_headers, key_time)
        headers = {
            "Authorization": (
                f"q-sign-algorithm=sha1&q-ak={settings.COS_SECRET_ID}"
                f"&q-sign-time={key_time}&q-key-time={key_time}"
                f"&q-header-list=x-cos-content-sha1&q-url-param-list=&q-signature={signature}"
            ),
            "Content-Type": content_type,
            "x-cos-content-sha1": content_sha1,
        }
        try:
            response = requests.request("PUT", url, data=content, headers=headers, timeout=30)
        except requests.RequestException:
            logger.exception("COS PUT请求异常: key=%s", cos_key)
            raise CosError("COS服务请求异常")
        if response.status_code != 200:
            logger.error("PUT Object失败: key=%s status=%s body=%s", cos_key, response.status_code, response.text[:300])
            raise CosError(f"PUT Object失败: HTTP {response.status_code}")
        return response.headers.get("ETag", "").strip('"')

    def generate_presigned_url(self, cos_key: str, expires: int = 3600) -> str:
        """生成 GET 预签名访问 URL（签名放查询参数，浏览器可直接访问）。

        Args:
            cos_key: COS 对象 Key。
            expires: 有效期（秒），默认3600。

        Returns:
            带签名的完整访问 URL 字符串。
        """
        url = self._build_object_url(cos_key)
        now = int(time.time())
        key_time = f"{now};{now + expires}"
        # 预签名URL：headers与params均参与空串签名（q-header-list/q-url-param-list为空）
        # 签名路径必须与URL中实际发送的编码后路径一致
        signature = self._calc_signature("get", self._path_from_url(url), "", "", key_time)
        params = {
            "q-sign-algorithm": "sha1",
            "q-ak": settings.COS_SECRET_ID,
            "q-sign-time": key_time,
            "q-key-time": key_time,
            "q-header-list": "",
            "q-url-param-list": "",
            "q-signature": signature,
        }
        return f"{url}?{urlencode(params)}"

    def get_appid(self) -> str:
        """从 Bucket 名称解析腾讯云 APPID（bucket 命名规范：{name}-{appid}）。

        Returns:
            APPID 字符串。
        """
        return settings.COS_BUCKET.rsplit("-", 1)[-1]

    def get_bucket_domain(self) -> str:
        """获取 Bucket 的默认访问域名（{bucket}.cos.{region}.myqcloud.com）。

        Returns:
            不含协议头的域名。
        """
        return f"{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com"

    # ------------------------------------------------------------------
    # 内部工具：COS XML API 签名与请求
    # ------------------------------------------------------------------

    def _build_object_url(self, cos_key: str) -> str:
        """构造对象完整访问 URL（Key 逐段 URL 编码，保留 / 分隔）。

        Args:
            cos_key: COS 对象 Key。

        Returns:
            完整 URL 字符串。
        """
        encoded_key = "/".join(quote(seg) for seg in cos_key.split("/"))
        return f"https://{self.get_bucket_domain()}/{encoded_key}"

    def _path_from_url(self, url: str) -> str:
        """从完整 URL 提取路径部分（含查询串前的编码后路径，以/开头）。

        Args:
            url: 完整请求 URL。

        Returns:
            URL 路径字符串（如 /resumes/123/xxx.pdf）。
        """
        return "/" + url.split("/", 3)[3].split("?")[0]

    def _signed_request(self, method: str, url: str, timeout: int = 10) -> requests.Response:
        """发起带 Authorization 签名头的 COS 请求（管理端永久密钥签名）。

        Args:
            method: HTTP 方法（HEAD/DELETE/GET 等）。
            url: 完整请求 URL。
            timeout: 请求超时（秒），下载对象等大响应场景可调大。

        Returns:
            requests.Response 响应对象。

        Raises:
            CosError: 请求异常（网络错误等）。
        """
        now = int(time.time())
        key_time = f"{now};{now + 600}"
        signature = self._calc_signature(method, self._path_from_url(url), "", "", key_time)
        headers = {
            "Authorization": (
                f"q-sign-algorithm=sha1&q-ak={settings.COS_SECRET_ID}"
                f"&q-sign-time={key_time}&q-key-time={key_time}"
                f"&q-header-list=&q-url-param-list=&q-signature={signature}"
            )
        }
        try:
            return requests.request(method, url, headers=headers, timeout=timeout)
        except requests.RequestException:
            logger.exception("COS请求异常: method=%s url=%s", method, url)
            raise CosError("COS服务请求异常")

    def _calc_signature(
        self,
        method: str,
        path: str,
        params_str: str,
        headers_str: str,
        key_time: str,
    ) -> str:
        """按 COS XML API 规范计算请求签名。

        算法: SignKey=HmacSHA1(SecretKey, KeyTime)，
              StringToSign=sha1\\n{KeyTime}\\n{SHA1(HttpString)}\\n，
              Signature=HmacSHA1(SignKey, StringToSign)，均取hex小写。
        HttpString 固定为 "HttpMethod\\nUriPathname\\nHttpParameters\\nHttpHeaders\\n"，
        其中某段为空时其前后换行符保留（如 "get\\n/path\\n\\n\\n"）。

        Args:
            method: HTTP 方法（小写参与签名）。
            path: URL 路径部分（以/开头）。
            params_str: 排序后的查询串（可为空）。
            headers_str: 排序后的请求头串（可为空）。
            key_time: 签名有效期区间，格式 {start};{end}。

        Returns:
            十六进制签名字符串。
        """
        secret_key = settings.COS_SECRET_KEY.encode("utf-8")
        sign_key = hmac.new(secret_key, key_time.encode("utf-8"), hashlib.sha1).hexdigest()
        http_string = f"{method.lower()}\n{path}\n{params_str}\n{headers_str}\n"
        string_to_sign = (
            f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
        )
        return hmac.new(sign_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).hexdigest()


# 模块级单例，供服务层直接引用
cos_client = CosClient()


def build_cos_url(cos_key: str) -> str:
    """构造对象的永久公网访问 URL（记录库中 cos_url 字段使用）。

    如果传入的已是完整 URL（以 https:// 开头），则原样返回。

    Args:
        cos_key: COS 对象 Key 或完整 URL。

    Returns:
        完整 URL 字符串。
    """
    if not cos_key:
        return ""
    if cos_key.startswith("http://") or cos_key.startswith("https://"):
        return cos_key
    return f"https://{cos_client.get_bucket_domain()}/{cos_key}"


def cos_key_from_url(url: str) -> str:
    """从完整 COS URL 中提取对象 Key（build_cos_url 的逆操作）。

    Args:
        url: 完整 URL 或本身就是 Key 的字符串。

    Returns:
        COS 对象 Key 字符串（无法解析时原样返回）。
    """
    if not url:
        return ""
    if not url.startswith("http://") and not url.startswith("https://"):
        return url
    # 形如 https://{bucket}.cos.{region}.myqcloud.com/{key}，取域名后路径
    parts = url.split("/", 3)
    return parts[3] if len(parts) == 4 else url


def format_upload_date() -> str:
    """获取当前 UTC 日期字符串（Redis 每日上传计数键使用）。

    Returns:
        格式为 YYYY-MM-DD 的字符串。
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")