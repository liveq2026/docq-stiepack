import {
  Dashboard as DashboardIcon,
  Description as DocumentsIcon,
  UploadFile as UploadIcon,
  PictureAsPdf as PdfIcon,
  PictureAsPdfOutlined as PdfDocumentsIcon,
  Settings as SettingsIcon,
} from "@mui/icons-material";
import {
  Box,
  Divider,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
} from "@mui/material";
import { useLocation, useNavigate } from "react-router-dom";

const DRAWER_WIDTH = 240;

const mainNavigation = [
  {
    label: "Dashboard",
    path: "/",
    icon: <DashboardIcon />,
  },
  {
    label: "Documents",
    path: "/documents",
    icon: <DocumentsIcon />,
  },
  {
    label: "Upload",
    path: "/upload",
    icon: <UploadIcon />,
  },
  {
    label: "PDF Upload",
    path: "/pdf-upload",
    icon: <PdfIcon />,
  },
  {
    label: "PDF Documents",
    path: "/pdf-documents",
    icon: <PdfDocumentsIcon />,
  },
];

const bottomNavigation = [
  {
    label: "Settings",
    path: "/settings",
    icon: <SettingsIcon />,
  },
];

function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  const isActive = (path: string) => {
    if (path === "/") {
      return location.pathname === "/";
    }

    return (
      location.pathname === path || location.pathname.startsWith(`${path}/`)
    );
  };

  const renderNavigationItem = (item: {
    label: string;
    path: string;
    icon: React.ReactNode;
  }) => {
    const active = isActive(item.path);

    return (
      <ListItem key={item.path} disablePadding>
        <ListItemButton
          selected={active}
          onClick={() => navigate(item.path)}
          sx={{
            mx: 1,
            my: 0.5,
            borderRadius: 1.5,
            minHeight: 44,
          }}
        >
          <ListItemIcon
            sx={{
              minWidth: 40,
              color: active ? "primary.main" : "text.secondary",
            }}
          >
            {item.icon}
          </ListItemIcon>

          <ListItemText
            primary={item.label}
            slotProps={{
              primary: {
                sx: {
                  fontSize: 14,
                  fontWeight: active ? 600 : 400,
                },
              },
            }}
          />
        </ListItemButton>
      </ListItem>
    );
  };

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,

        "& .MuiDrawer-paper": {
          width: DRAWER_WIDTH,
          boxSizing: "border-box",
          borderRight: "1px solid",
          borderColor: "divider",
        },
      }}
    >
      {/* =========================================================
          BRAND
          ========================================================= */}

      <Box
        sx={{
          height: 64,
          display: "flex",
          alignItems: "center",
          px: 2.5,
        }}
      >
        <Typography
          variant="h6"
          sx={{
            fontWeight: 700,
            letterSpacing: "-0.5px",
          }}
        >
          DOCQ
        </Typography>
      </Box>

      <Divider />

      {/* =========================================================
          MAIN NAVIGATION
          ========================================================= */}

      <Box sx={{ pt: 1.5 }}>
        <List disablePadding>{mainNavigation.map(renderNavigationItem)}</List>
      </Box>

      {/* =========================================================
          BOTTOM NAVIGATION
          ========================================================= */}

      <Box sx={{ mt: "auto", pb: 1.5 }}>
        <Divider sx={{ mb: 1 }} />

        <List disablePadding>{bottomNavigation.map(renderNavigationItem)}</List>
      </Box>
    </Drawer>
  );
}

export default Sidebar;
