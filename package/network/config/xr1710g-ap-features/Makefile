# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk
PKG_NAME:=xr1710g-ap-features
PKG_RELEASE:=8
PKG_LICENSE:=GPL-2.0-only
PKGARCH:=all
include $(INCLUDE_DIR)/package.mk
define Package/xr1710g-ap-features
  SECTION:=net
  CATEGORY:=Network
  TITLE:=XR1710G AP13 optional features and performance diagnostics
  DEPENDS:=+uci +libubox +jsonfilter +ubus +usteer +luci-base +xr1710g-ap-configurator
endef
define Build/Compile
endef
define Package/xr1710g-ap-features/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/init.d $(1)/usr/libexec/rpcd
	$(INSTALL_BIN) ./files/xr1710g-ap-features $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/xr1710g-ap-feature-control $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/xr1710g-ap-perf $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/xr1710g_ap_features $(1)/etc/init.d/
	$(INSTALL_BIN) ./files/luci.xr1710g_ap_features $(1)/usr/libexec/rpcd/
	$(INSTALL_DIR) $(1)/usr/share/rpcd/acl.d $(1)/usr/share/luci/menu.d
	$(INSTALL_DATA) ./files/luci-app-xr1710g-features.json $(1)/usr/share/rpcd/acl.d/
	$(INSTALL_DATA) ./files/menu.json $(1)/usr/share/luci/menu.d/luci-app-xr1710g-features.json
	$(INSTALL_DIR) $(1)/www/luci-static/resources/view/xr1710g
	$(INSTALL_DATA) ./files/features.js $(1)/www/luci-static/resources/view/xr1710g/
endef
$(eval $(call BuildPackage,xr1710g-ap-features))
