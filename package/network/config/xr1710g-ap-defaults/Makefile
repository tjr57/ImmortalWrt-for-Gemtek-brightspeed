# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk

PKG_NAME:=xr1710g-ap-defaults
PKG_RELEASE:=7
PKG_LICENSE:=GPL-2.0-only
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/xr1710g-ap-defaults
  SECTION:=net
  CATEGORY:=Network
  TITLE:=XR1710G per-device AP defaults
  DEPENDS:=@(TARGET_airoha_an7581_DEVICE_gemtek_xr1710g||TARGET_DEVICE_airoha_an7581_DEVICE_gemtek_xr1710g)
endef

define Package/xr1710g-ap-defaults/conffiles
/etc/config/xr1710g_ap
endef

define Build/Compile
endef

define Package/xr1710g-ap-defaults/install
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/uci-defaults
	$(INSTALL_DATA) ./files/xr1710g-ap-profile $(1)/etc/xr1710g-ap-profile
	$(INSTALL_DATA) ./files/xr1710g_ap $(1)/etc/config/xr1710g_ap
	$(INSTALL_BIN) ./files/95-xr1710g-ap $(1)/etc/uci-defaults/95-xr1710g-ap
	$(INSTALL_BIN) ./files/96-xr1710g-ap-fan $(1)/etc/uci-defaults/96-xr1710g-ap-fan
	$(INSTALL_BIN) ./files/97-xr1710g-admin-defaults $(1)/etc/uci-defaults/97-xr1710g-admin-defaults
	$(INSTALL_DIR) $(1)/usr/lib/xr1710g $(1)/usr/sbin $(1)/etc/init.d $(1)/etc/rc.d
	$(INSTALL_DATA) ./files/ap-role.sh $(1)/usr/lib/xr1710g/ap-role.sh
	$(INSTALL_BIN) ./files/xr1710g-ap-role $(1)/usr/sbin/xr1710g-ap-role
endef

$(eval $(call BuildPackage,xr1710g-ap-defaults))
