package com.remotemountains.canyon;

import com.remotemountains.cliff.CliffPatch;
import com.remotemountains.cliff.CliffPlacement;
import com.remotemountains.cliff.Vec3;
import com.remotemountains.watershed.WatershedTerrainSource;
import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.BasicStroke;
import java.awt.image.BufferedImage;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import javax.imageio.ImageIO;

/** Exports the completed canyon charts used by the VDM modifier. */
public final class CanyonPreview {
    private static final int SCALE = 3;
    private static final int GAP = 18;

    public static void main(String[] args) throws Exception {
        long seed = 20260927L;
        Path output = Path.of("preview/canyon");
        Files.createDirectories(output);
        var base = new WatershedTerrainSource(seed, "");
        var canyon = new CanyonCliffModifier(base, seed, true);
        var sites = canyon.placements();
        int panelWidth = 161 * SCALE;
        int panelHeight = 81 * SCALE;
        int rowHeight = panelHeight + 58;
        int width = GAP * 4 + panelWidth * 3;
        int height = 62 + sites.size() * rowHeight;
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = image.createGraphics();
        g.setColor(new Color(16, 27, 35));
        g.fillRect(0, 0, width, height);
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setFont(new Font("SansSerif", Font.BOLD, 19));
        g.setColor(Color.WHITE);
        g.drawString("Canyon valley sides: actual completed surface charts", GAP, 27);
        g.setFont(new Font("SansSerif", Font.PLAIN, 13));
        g.drawString("Base terrain  |  sculpted vertices  |  vertex elevation change (blue lower, rust higher)", GAP, 47);
        StringBuilder csv = new StringBuilder("site,row,column,base_x,base_y,base_z,sculpted_x,sculpted_y,sculpted_z,delta_y,normal_x,normal_y,normal_z,reference_angle_degrees\n");
        for (int index = 0; index < sites.size(); index++) {
            CliffPlacement site = sites.get(index);
            CliffPatch chart = canyon.result(index).patch();
            int top = 62 + index * rowHeight;
            double[][] before = new double[chart.rows][chart.columns];
            double[][] after = new double[chart.rows][chart.columns];
            double[][] delta = new double[chart.rows][chart.columns];
            double min = Double.POSITIVE_INFINITY, max = Double.NEGATIVE_INFINITY;
            for (int row = 0; row < chart.rows; row++) for (int col = 0; col < chart.columns; col++) {
                int vertex = chart.index(col, row);
                Vec3 localBase = new Vec3(256, 0, 256)
                    .add(CliffPatch.ALONG.scale(chart.u(col)))
                    .add(CliffPatch.OUT.scale(chart.v(row)));
                Vec3 baseWorld = site.toWorld(localBase.x(), localBase.z());
                Vec3 sculpted = chart.position(vertex);
                Vec3 sculptedWorld = site.toWorld(sculpted.x(), sculpted.z());
                Vec3 normal = chart.normal(vertex);
                double baseHeight = base.sample(baseWorld.x(), baseWorld.z()).height();
                before[row][col] = baseHeight;
                after[row][col] = sculpted.y();
                delta[row][col] = sculpted.y() - baseHeight;
                min = Math.min(min, Math.min(baseHeight, sculpted.y()));
                max = Math.max(max, Math.max(baseHeight, sculpted.y()));
                csv.append(String.format(Locale.ROOT,
                    "%d,%d,%d,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,%.2f%n",
                    index, row, col, baseWorld.x(), baseHeight, baseWorld.z(),
                    sculptedWorld.x(), sculpted.y(), sculptedWorld.z(), delta[row][col],
                    normal.x(), normal.y(), normal.z(), site.settings().angleDegrees()));
            }
            drawPanel(g, before, GAP, top, min, max, false);
            drawPanel(g, after, GAP * 2 + panelWidth, top, min, max, false);
            drawPanel(g, delta, GAP * 3 + panelWidth * 2, top, -42, 42, true);
            g.setColor(Color.WHITE);
            g.setFont(new Font("SansSerif", Font.BOLD, 14));
            g.drawString(String.format(Locale.ROOT,
                "Side %d  |  reference angle %.0f deg  |  center (%.0f, %.0f)",
                index + 1, site.settings().angleDegrees(), site.x(), site.z()),
                GAP, top + panelHeight + 22);
            g.setFont(new Font("SansSerif", Font.PLAIN, 12));
            g.setColor(new Color(190, 206, 214));
            g.drawString("Angle setting is relative to the sloped base; final local face angles vary.",
                GAP, top + panelHeight + 40);
        }
        g.dispose();
        Files.writeString(output.resolve("surface-vertices.csv"), csv);
        ImageIO.write(image, "png", output.resolve("surfaces.png").toFile());
        writeProfiles(output, base, canyon);
        System.out.println(output.toAbsolutePath());
    }

    private static void writeProfiles(Path output, WatershedTerrainSource base,
                                      CanyonCliffModifier canyon) throws Exception {
        int width = 1060, rowHeight = 230;
        BufferedImage image = new BufferedImage(width, 42 + canyon.placements().size() * rowHeight,
            BufferedImage.TYPE_INT_RGB);
        Graphics2D g = image.createGraphics();
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setColor(new Color(17, 29, 38));
        g.fillRect(0, 0, image.getWidth(), image.getHeight());
        g.setColor(Color.WHITE);
        g.setFont(new Font("SansSerif", Font.BOLD, 17));
        g.drawString("Canyon side profiles: original ground and completed chart geometry", 24, 28);
        StringBuilder csv = new StringBuilder("site,row,base_out,base_height,sculpted_out,sculpted_height\n");
        for (int index = 0; index < canyon.placements().size(); index++) {
            CliffPlacement site = canyon.placements().get(index);
            CliffPatch chart = canyon.result(index).patch();
            double[] baseOut = new double[chart.rows], baseY = new double[chart.rows];
            double[] sculptOut = new double[chart.rows], sculptY = new double[chart.rows];
            double minY = Double.POSITIVE_INFINITY, maxY = Double.NEGATIVE_INFINITY;
            int col = chart.columns / 2;
            for (int row = 0; row < chart.rows; row++) {
                Vec3 originalLocal = new Vec3(256, 0, 256).add(CliffPatch.OUT.scale(chart.v(row)));
                Vec3 originalWorld = site.toWorld(originalLocal.x(), originalLocal.z());
                Vec3 finalLocal = chart.position(chart.index(col, row));
                Vec3 finalWorld = site.toWorld(finalLocal.x(), finalLocal.z());
                baseOut[row] = chart.v(row);
                baseY[row] = base.sample(originalWorld.x(), originalWorld.z()).height();
                Vec3 displacement = finalWorld.subtract(new Vec3(site.x(), 0, site.z()));
                sculptOut[row] = displacement.dot(site.rotate(CliffPatch.OUT));
                sculptY[row] = finalLocal.y();
                minY = Math.min(minY, Math.min(baseY[row], sculptY[row]));
                maxY = Math.max(maxY, Math.max(baseY[row], sculptY[row]));
                csv.append(String.format(Locale.ROOT, "%d,%d,%.6f,%.6f,%.6f,%.6f%n",
                    index, row, baseOut[row], baseY[row], sculptOut[row], sculptY[row]));
            }
            int top = 42 + index * rowHeight;
            int plotLeft = 54, plotRight = width - 32, plotTop = top + 34, plotBottom = top + 198;
            g.setColor(new Color(31, 48, 57));
            g.fillRect(plotLeft, plotTop, plotRight - plotLeft, plotBottom - plotTop);
            g.setColor(new Color(99, 120, 127));
            g.setStroke(new BasicStroke(1));
            g.drawLine(plotLeft, plotBottom, plotRight, plotBottom);
            g.drawLine(plotLeft, plotTop, plotLeft, plotBottom);
            minY -= 8;
            maxY += 8;
            drawProfile(g, baseOut, baseY, plotLeft, plotRight, plotTop, plotBottom,
                minY, maxY, new Color(138, 183, 163));
            drawProfile(g, sculptOut, sculptY, plotLeft, plotRight, plotTop, plotBottom,
                minY, maxY, new Color(239, 165, 89));
            g.setFont(new Font("SansSerif", Font.BOLD, 13));
            g.setColor(Color.WHITE);
            g.drawString(String.format(Locale.ROOT, "Side %d, reference angle %.0f deg",
                index + 1, site.settings().angleDegrees()), plotLeft, top + 18);
            g.setFont(new Font("SansSerif", Font.PLAIN, 12));
            g.setColor(new Color(138, 183, 163));
            g.drawString("original ground", plotRight - 240, top + 18);
            g.setColor(new Color(239, 165, 89));
            g.drawString("completed cliff", plotRight - 120, top + 18);
            g.setColor(new Color(170, 187, 193));
            g.drawString("-80", plotLeft - 10, plotBottom + 16);
            g.drawString("+80 blocks across valley side", plotRight - 166, plotBottom + 16);
        }
        g.dispose();
        Files.writeString(output.resolve("center-profiles.csv"), csv);
        ImageIO.write(image, "png", output.resolve("profiles.png").toFile());
    }

    private static void drawProfile(Graphics2D g, double[] xs, double[] ys,
                                    int left, int right, int top, int bottom,
                                    double minY, double maxY, Color color) {
        g.setColor(color);
        g.setStroke(new BasicStroke(3, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
        for (int i = 1; i < xs.length; i++) {
            int x0 = (int) (left + (xs[i - 1] + 80) / 160 * (right - left));
            int x1 = (int) (left + (xs[i] + 80) / 160 * (right - left));
            int y0 = (int) (bottom - (ys[i - 1] - minY) / (maxY - minY) * (bottom - top));
            int y1 = (int) (bottom - (ys[i] - minY) / (maxY - minY) * (bottom - top));
            g.drawLine(x0, y0, x1, y1);
        }
    }

    private static void drawPanel(Graphics2D g, double[][] values, int left, int top,
                                  double min, double max, boolean difference) {
        for (int row = 0; row < values.length; row++) for (int col = 0; col < values[row].length; col++) {
            double value = values[row][col];
            Color color;
            if (difference) {
                double t = Math.min(1, Math.abs(value) / 32);
                color = value < 0
                    ? blend(new Color(207, 213, 203), new Color(41, 104, 174), t)
                    : blend(new Color(207, 213, 203), new Color(173, 78, 42), t);
            } else {
                double t = Math.max(0, Math.min(1, (value - min) / Math.max(1, max - min)));
                double dx = values[row][Math.min(values[row].length - 1, col + 1)]
                    - values[row][Math.max(0, col - 1)];
                double dz = values[Math.min(values.length - 1, row + 1)][col]
                    - values[Math.max(0, row - 1)][col];
                double shade = Math.max(.56, Math.min(1.28, .96 + .032 * (dx - dz)));
                color = new Color(channel((64 + 144 * t) * shade),
                    channel((92 + 135 * t) * shade), channel((68 + 116 * t) * shade));
            }
            g.setColor(color);
            g.fillRect(left + col * SCALE, top + row * SCALE, SCALE, SCALE);
        }
    }

    private static Color blend(Color a, Color b, double t) {
        return new Color(channel(a.getRed() * (1 - t) + b.getRed() * t),
            channel(a.getGreen() * (1 - t) + b.getGreen() * t),
            channel(a.getBlue() * (1 - t) + b.getBlue() * t));
    }

    private static int channel(double value) {
        return (int) Math.max(0, Math.min(255, value));
    }
}
