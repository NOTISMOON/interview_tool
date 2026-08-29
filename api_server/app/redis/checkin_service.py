"""签到服务模块，基于Redis Bitmap实现每日签到与连续天数统计。

Redis键设计:
    checkin:user:{user_id}:{year}{month}  →  BITMAP，第 day 位标记当天签到
    checkin:total:{user_id}                →  总签到天数（递增计数器）

连续天数计算逻辑:
    从今天往前遍历，直到遇到未签到的日期为止。
"""

from datetime import date, timedelta

from redis import Redis


class CheckinService:
    """签到服务，封装Redis Bitmap操作。"""

    BITMAP_PREFIX = "checkin:user:"
    TOTAL_KEY_PREFIX = "checkin:total:"

    def __init__(self, redis: Redis) -> None:
        """初始化签到服务。

        Args:
            redis: 同步Redis客户端。
        """
        self.redis = redis

    @staticmethod
    def _bitmap_key(user_id: int, dt: date) -> str:
        """构建月度Bitmap键。

        Args:
            user_id: 用户ID。
            dt: 日期。

        Returns:
            Redis键，如 checkin:user:1:202608。
        """
        return f"{CheckinService.BITMAP_PREFIX}{user_id}:{dt.strftime('%Y%m')}"

    @staticmethod
    def _total_key(user_id: int) -> str:
        """构建总签到天数键。

        Args:
            user_id: 用户ID。

        Returns:
            Redis键，如 checkin:total:1。
        """
        return f"{CheckinService.TOTAL_KEY_PREFIX}{user_id}"

    def _is_signed_in(self, user_id: int, dt: date) -> bool:
        """检查指定日期是否已签到。

        Args:
            user_id: 用户ID。
            dt: 日期。

        Returns:
            True表示已签到，False表示未签到。
        """
        key = self._bitmap_key(user_id, dt)
        bit = self.redis.getbit(key, dt.day)
        return bool(bit)

    def _calculate_streak(self, user_id: int) -> int:
        """计算连续签到天数。

        Args:
            user_id: 用户ID。

        Returns:
            连续签到天数。
        """
        today = date.today()
        streak = 0
        # 从今天往回遍历，遇到未签到即停止
        for i in range(366):  # 最大遍历一年
            d = today - timedelta(days=i)
            if self._is_signed_in(user_id, d):
                streak += 1
            else:
                break
        return streak

    def get_status(self, user_id: int) -> dict:
        """获取签到状态。

        Args:
            user_id: 用户ID。

        Returns:
            dict: {"signedIn": bool, "streak": int, "totalDays": int}。
        """
        today = date.today()
        signed_in = self._is_signed_in(user_id, today)
        streak = self._calculate_streak(user_id) if signed_in else 0
        total = int(self.redis.get(self._total_key(user_id)) or 0)
        return {"signedIn": signed_in, "streak": streak, "totalDays": total}

    def checkin(self, user_id: int) -> dict:
        """执行签到。

        Args:
            user_id: 用户ID。

        Returns:
            dict: 签到后的状态 {"signedIn": true, "streak": int, "totalDays": int}。
        """
        today = date.today()
        key = self._bitmap_key(user_id, today)
        total_key = self._total_key(user_id)

        # 已签到则直接返回状态
        if self._is_signed_in(user_id, today):
            return self.get_status(user_id)

        # 设置当天签到位
        self.redis.setbit(key, today.day, 1)
        # 设置30天过期，自动清理旧数据
        self.redis.expire(key, 86400 * 31)
        # 递增总天数
        self.redis.incr(total_key)

        streak = self._calculate_streak(user_id)
        total = int(self.redis.get(total_key) or 0)
        return {"signedIn": True, "streak": streak, "totalDays": total}