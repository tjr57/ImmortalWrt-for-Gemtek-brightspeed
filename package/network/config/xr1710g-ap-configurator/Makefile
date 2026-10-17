# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk

PKG_NAME:=xr1710g-ap-configurator
PKG_RELEASE:=10
PKG_LICENSE:=GPL-2.0-only
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/xr1710g-ap-configurator
  SECTION:=net
  CATEGORY:=Network
  TITLE:=XR1710G staged AP and VLAN configuration
  DEPENDS:=+uci +netifd +jsonfilter +ubus +xr1710g-ap-defaults
endef

define Package/xr1710g-ap-configurator/conffiles
/etc/config/xr1710g_ap_configurator
endef

define Build/Compile
endef

define Package/xr1710g-ap-configurator/install
	$(INSTALL_DIR) $(1)/etc/config $(1)/usr/sbin
	$(INSTALL_CONF) ./files/xr1710g_ap_configurator $(1)/etc/config/xr1710g_ap_configurator
	chmod 0600 $(1)/etc/config/xr1710g_ap_configurator
	$(INSTALL_BIN) ./files/xr1710g-ap-configure $(1)/usr/sbin/xr1710g-ap-configure
	$(INSTALL_BIN) ./files/xr1710g-ap-uplink-guard $(1)/usr/sbin/xr1710g-ap-uplink-guard
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/xr1710g_ap_uplink_guard $(1)/etc/init.d/xr1710g_ap_uplink_guard

endef

$(eval $(call BuildPackage,xr1710g-ap-configurator))
