from django.apps import AppConfig


class OpportunitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.opportunities"

    def ready(self) -> None:
        from .audit_schemas import register_opportunity_audit_schemas
        from .checks.adapters import MANUAL_UNSUPPORTED_ADAPTER, register_adapter
        from .checks.alibaba import ALIBABA_CAMPUS_ADAPTER
        from .checks.antgroup import ANTGROUP_ADAPTER
        from .checks.beisen import BEISEN_ZHIYE_ADAPTER
        from .checks.brainco import BRAINCO_ADAPTER
        from .checks.bytedance import BYTEDANCE_CAMPUS_ADAPTER
        from .checks.czbank import CZBANK_ADAPTER
        from .checks.dahua import DAHUA_ADAPTER
        from .checks.deepseek import DEEPSEEK_ADAPTER
        from .checks.getui import GETUI_ADAPTER
        from .checks.hikvision import HIKVISION_ADAPTER
        from .checks.huawei import HUAWEI_ADAPTER
        from .checks.hzbank import HZBANK_ADAPTER
        from .checks.jd import JD_CAMPUS_ADAPTER
        from .checks.kujiale import KUJIALE_ADAPTER
        from .checks.leihuo import NETEASE_LEIHUO_ADAPTER
        from .checks.meituan import MEITUAN_ADAPTER
        from .checks.moka import MOKA_ADAPTER
        from .checks.netease import NETEASE_HR_ADAPTER
        from .checks.netease_game import NETEASE_GAME_ADAPTER
        from .checks.tencent import TENCENT_ADAPTER
        from .checks.unitree import UNITREE_ADAPTER
        from .checks.xiaomi import XIAOMI_CAMPUS_ADAPTER, XIAOMI_INTERN_ADAPTER

        register_adapter(MANUAL_UNSUPPORTED_ADAPTER)
        register_adapter(ALIBABA_CAMPUS_ADAPTER)
        register_adapter(ANTGROUP_ADAPTER)
        register_adapter(BEISEN_ZHIYE_ADAPTER)
        register_adapter(BRAINCO_ADAPTER)
        register_adapter(BYTEDANCE_CAMPUS_ADAPTER)
        register_adapter(CZBANK_ADAPTER)
        register_adapter(DAHUA_ADAPTER)
        register_adapter(DEEPSEEK_ADAPTER)
        register_adapter(GETUI_ADAPTER)
        register_adapter(HZBANK_ADAPTER)
        register_adapter(HUAWEI_ADAPTER)
        register_adapter(HIKVISION_ADAPTER)
        register_adapter(JD_CAMPUS_ADAPTER)
        register_adapter(KUJIALE_ADAPTER)
        register_adapter(MEITUAN_ADAPTER)
        register_adapter(MOKA_ADAPTER)
        register_adapter(NETEASE_LEIHUO_ADAPTER)
        register_adapter(NETEASE_HR_ADAPTER)
        register_adapter(NETEASE_GAME_ADAPTER)
        register_adapter(TENCENT_ADAPTER)
        register_adapter(UNITREE_ADAPTER)
        register_adapter(XIAOMI_CAMPUS_ADAPTER)
        register_adapter(XIAOMI_INTERN_ADAPTER)
        register_opportunity_audit_schemas()
