"""用户服务模块，封装用户管理的业务逻辑与Redis缓存（同步）。

缓存策略（Cache-Aside）:
    读: 先查Redis → 未命中查数据库 → 回填缓存 → 返回。
    写: 先更新数据库（事务提交）→ 再删除缓存，下次查询自然回填最新数据。

Redis键设计:
    user:profile:{user_id} → 完整资料JSON（含可见性），TTL由配置项控制。
    说明: 缓存存完整资料而非按访问者裁剪后的版本，避免同一份数据多份缓存；
    字段可见性过滤在Service层按访问者身份进行。
"""

import json
import logging

import redis
from sqlalchemy.orm import Session

from app.cache.follow_cache import follow_cache, DIRECTION_FOLLOWING
from app.core.config import settings
from app.repositories.outbox_repository import sync_outbox_repository
from app.repositories.user_repository import sync_user_repository
from app.repositories.user_settings_repository import user_settings_repository
from app.schemas.user import (
    ProfileVisibilityUpdateRequest,
    UserCardResponse,
    UserProfileResponse,
    UserPublicProfileResponse,
    UserUpdateRequest,
)

logger = logging.getLogger(__name__)

# 用户资料缓存键前缀
USER_PROFILE_CACHE_PREFIX = "user:profile:"
# 已注销用户吊销标记键前缀（refresh流程校验，防止注销后用旧refresh_token续签）
USER_DEACTIVATED_PREFIX = "user:deactivated:"


class UserService:
    """用户业务逻辑层（同步），实现Cache-Aside缓存读写。"""

    @staticmethod
    def _build_cache_key(user_id: int) -> str:
        """构建用户资料缓存键。

        Args:
            user_id: 用户唯一标识。

        Returns:
            Redis键名，如 user:profile:123。
        """
        return f"{USER_PROFILE_CACHE_PREFIX}{user_id}"

    def _get_profile_from_cache(self, cache_client: redis.Redis, user_id: int) -> UserProfileResponse | None:
        """从Redis读取缓存的用户资料。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户唯一标识。

        Returns:
            缓存命中的UserProfileResponse，未命中返回None。
        """
        raw = cache_client.get(self._build_cache_key(user_id))
        if raw is None:
            return None
        return UserProfileResponse.model_validate(json.loads(raw))

    def _fill_profile_cache(self, cache_client: redis.Redis, profile: UserProfileResponse) -> None:
        """将用户资料回填Redis缓存并设置TTL。

        Args:
            cache_client: 同步Redis客户端。
            profile: 用户完整资料响应模型。
        """
        cache_client.setex(
            self._build_cache_key(profile.id),
            settings.USER_PROFILE_CACHE_TTL,
            profile.model_dump_json(),
        )

    def invalidate_profile_cache(self, cache_client: redis.Redis, user_id: int) -> None:
        """删除用户资料缓存（数据库更新成功后调用）。

        Args:
            cache_client: 同步Redis客户端。
            user_id: 用户唯一标识。
        """
        cache_client.delete(self._build_cache_key(user_id))
        logger.info("已删除用户资料缓存: user_id=%s", user_id)

    def get_profile(self, db: Session, cache_client: redis.Redis, user_id: int) -> UserProfileResponse | None:
        """获取个人信息（Cache-Aside：先查缓存，未命中查库并回填）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            user_id: 用户唯一标识。

        Returns:
            UserProfileResponse，用户不存在或已注销返回None。
        """
        # 1. 先查缓存
        cached = self._get_profile_from_cache(cache_client, user_id)
        if cached is not None:
            return cached

        # 2. 缓存未命中 → 查数据库
        user = sync_user_repository.get_by_id(db, user_id)
        if user is None:
            return None

        # 3. 回填缓存后返回
        profile = UserProfileResponse.model_validate(user)
        # 补充user_settings表中的可见性字段
        settings = user_settings_repository.get_or_create(db, user_id)
        profile.visibility_gender = settings.visibility_gender
        profile.visibility_birthday = settings.visibility_birthday
        profile.visibility_bio = settings.visibility_bio
        profile.visibility_location = settings.visibility_location
        profile.visibility_phone = settings.visibility_phone
        self._fill_profile_cache(cache_client, profile)
        return profile

    def update_profile(
        self,
        db: Session,
        cache_client: redis.Redis,
        user_id: int,
        payload: UserUpdateRequest,
    ) -> UserProfileResponse | None:
        """更新个人资料：先更新数据库，事务提交后删除缓存。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            user_id: 用户唯一标识。
            payload: 待更新字段请求模型。

        Returns:
            更新后的UserProfileResponse，用户不存在返回None。
        """
        update_data = payload.model_dump(exclude_unset=True)
        try:
            with db.begin():
                sync_user_repository.update_profile(db, user_id, update_data)
        except Exception:
            logger.exception("更新用户资料失败: user_id=%s", user_id)
            raise

        # 数据库更新成功后再删缓存，下次查询回填最新数据
        self.invalidate_profile_cache(cache_client, user_id)
        return self.get_profile(db, cache_client, user_id)

    def update_profile_visibility(
        self,
        db: Session,
        cache_client: redis.Redis,
        user_id: int,
        payload: ProfileVisibilityUpdateRequest,
    ) -> UserProfileResponse | None:
        """更新资料可见性：先更新数据库，事务提交后删除缓存。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            user_id: 用户唯一标识。
            payload: 可见性更新请求模型。

        Returns:
            更新后的UserProfileResponse，用户不存在返回None。
        """
        try:
            with db.begin():
                update_data = payload.model_dump(exclude_unset=True)
                user_settings_repository.get_or_create(db, user_id)
                user_settings_repository.update(db, user_id, update_data)
        except Exception:
            logger.exception("更新用户资料可见性失败: user_id=%s", user_id)
            raise

        self.invalidate_profile_cache(cache_client, user_id)
        return self.get_profile(db, cache_client, user_id)

    def get_public_profile(
        self,
        db: Session,
        cache_client: redis.Redis,
        target_user_id: int,
        viewer_id: int | None,
    ) -> UserPublicProfileResponse | UserCardResponse | None:
        """获取他人公开资料，按目标用户可见性设置过滤返回字段。

        可见性规则:
            - 本人访问（viewer_id == target_user_id）→ 返回完整公开资料。
            - visibility=0 公开 → 返回完整公开资料。
            - visibility=1 仅关注者 → 关注者返回完整公开资料，否则返回仅含
              昵称/头像的受限卡片（前端可提示"仅对关注者开放"）。
            - visibility=2 仅自己 → 非本人视为不存在，返回None。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            target_user_id: 被查看的用户ID。
            viewer_id: 当前访问者ID（游客为None）。

        Returns:
            UserPublicProfileResponse或UserCardResponse，用户不存在/已注销/不可见返回None。
        """
        profile = self.get_profile(db, cache_client, target_user_id)
        if profile is None:
            return None

        # 本人访问 → 完整公开资料（自己对自己不显示关注关系）
        if viewer_id is not None and viewer_id == target_user_id:
            return UserPublicProfileResponse.model_validate(profile)

        if profile.profile_visibility == 2:
            # 仅自己可见 → 对外等同于不存在
            return None

        if profile.profile_visibility == 1:
            # 仅关注者可见 → 校验关注关系（游客视为未关注）
            is_follower = viewer_id is not None and sync_user_repository.is_following(db, viewer_id, target_user_id)
            if not is_follower:
                return UserCardResponse.model_validate(profile)

        # 关注关系基于 Redis 判断（SET + SMISMEMBER，与关注/粉丝列表同源）
        # 前置保障：与 follow_service 列表页一致，先确保 viewer 的 following SET
        # 已回源，否则未回源时 SMISMEMBER 空返回会误报"已关注却显示未关注"。
        is_following = False
        if viewer_id is not None:
            follow_cache.rebuild_set(cache_client, db, viewer_id, DIRECTION_FOLLOWING)
            flags = follow_cache.batch_relation_flags(cache_client, viewer_id, [target_user_id])
            is_following = flags[0]["is_following"]

        resp = UserPublicProfileResponse.model_validate(profile)
        resp.is_following = is_following
        return resp

    def delete_account(self, db: Session, cache_client: redis.Redis, user_id: int) -> bool:
        """注销账号（软删除）：单事务内软删除用户、清理双向关注关系、修正计数并写注销事件。

        事务步骤:
            1. user.status 置为2（注销）。
            2. 删除该用户所有关注关系（作为关注者与被关注者两个方向）。
            3. 批量修正关联用户冗余计数（被我关注的人粉丝数-1、我的粉丝关注数-1）。
            4. 写入 user_deactivated Outbox事件（同一事务），由Consumer清理
               该用户的关注/粉丝缓存及其双向关联键成员（闭环读路径B-14）。

        Args:
            db: 数据库同步会话。
            cache_client: 同步Redis客户端。
            user_id: 用户唯一标识。

        Returns:
            注销成功返回True，用户不存在或已注销返回False。
        """
        try:
            with db.begin():
                # 前置校验：仅正常状态用户可注销
                user = sync_user_repository.get_by_id(db, user_id)
                if user is None or user.status != 1:
                    return False

                # 注销前先取双向关注关系，用于事务内修正计数与事件payload
                # （必须在删除关系前采集，删除后Consumer无法反查）
                following_ids = sync_user_repository.get_following_ids(db, user_id)
                follower_ids = sync_user_repository.get_follower_ids(db, user_id)

                sync_user_repository.soft_delete(db, user_id)
                sync_user_repository.delete_follow_relations(db, user_id)
                # 我关注的人：粉丝数-1；我的粉丝：关注数-1
                sync_user_repository.decrement_followers_count(db, following_ids)
                sync_user_repository.decrement_following_count(db, follower_ids)

                # 注销事件（同一事务）：payload带双向ID列表，超上限截断靠缓存TTL自愈
                payload_limit = settings.OUTBOX_DEACTIVATED_PAYLOAD_LIMIT
                truncated = len(following_ids) > payload_limit or len(follower_ids) > payload_limit
                sync_outbox_repository.insert_event(
                    db,
                    event_type="user_deactivated",
                    aggregate_type="user",
                    aggregate_id=str(user_id),
                    payload={
                        "user_id": user_id,
                        "following_ids": following_ids[:payload_limit],
                        "follower_ids": follower_ids[:payload_limit],
                        "truncated": truncated,
                    },
                )
        except Exception:
            logger.exception("注销账号失败: user_id=%s", user_id)
            raise

        # 事务提交后删除缓存，已注销用户后续查询将查库并得到None
        self.invalidate_profile_cache(cache_client, user_id)
        # 写入注销吊销标记（有效期覆盖refresh_token最长寿命），refresh续签时校验拒绝
        cache_client.setex(
            f"{USER_DEACTIVATED_PREFIX}{user_id}",
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            "1",
        )
        logger.info("账号已注销: user_id=%s", user_id)
        return True


user_service = UserService()