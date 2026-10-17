include $(TOPDIR)/rules.mk

PKG_NAME:=xr-ppe-l2
PKG_RELEASE:=5
PKG_LICENSE:=GPL-2.0-only
PKG_MAINTAINER:=XR1710G Maintainer

include $(INCLUDE_DIR)/package.mk

define Package/xr-ppe-l2
  SECTION:=net
  CATEGORY:=Network
  TITLE:=XR1710G PPE bridge template publisher and coherent collector
  DEPENDS:=@TARGET_airoha
endef

define Package/xr-ppe-l2/description
  Client for the airoha xr_ppe_l2 generic netlink owner of PPE bridge
  templates: state, publish, revoke, coherent collect and reconcile.
  Templates stay inert while the boot-only PPE bind permissions are off.
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CPPFLAGS) $(TARGET_CFLAGS) -Wall -Wextra -Werror \
		$(TARGET_LDFLAGS) -o $(PKG_BUILD_DIR)/xr-ppe-l2 ./src/xr-ppe-l2.c
endef

define Package/xr-ppe-l2/conffiles
/etc/config/xr_ppe_l2
/etc/xr-ppe-l2.desired
endef

define Package/xr-ppe-l2/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/config $(1)/etc/init.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/xr-ppe-l2 $(1)/usr/sbin/
	$(INSTALL_CONF) ./files/xr_ppe_l2.config $(1)/etc/config/xr_ppe_l2
	$(INSTALL_CONF) ./files/xr-ppe-l2.desired $(1)/etc/xr-ppe-l2.desired
	$(INSTALL_BIN) ./files/xr-ppe-l2.init $(1)/etc/init.d/xr-ppe-l2
endef

$(eval $(call BuildPackage,xr-ppe-l2))
